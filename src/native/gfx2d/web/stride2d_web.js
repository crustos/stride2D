// stride2d_web.js: runs a Stride2D player built for a page (`python3 build.py player GAME --web`) and draws for it.
//
//   <canvas id="screen"></canvas>  +  startStride2D({ wasm: "stride2d-player.wasm", canvas, log })
//
// The module is a WASI "reactor": it has no main loop of its own. This loads it, gives it a small WASI (stdout goes to `log`; there is no file system)
// and the "gfx" imports of src/native/gfx2d/gfx2d_web.c, which draw right here, with WebGPU when the browser has it and WebGL2 otherwise (the `gfx`
// option, or `?gfx=webgpu` / `?gfx=webgl2` in the page's URL; the default, "auto", prefers WebGPU). It then calls the module's exports stride2d_init()
// once and stride2d_frame() once per 1/60 s of game time: a fixed step, whatever the display's refresh rate is.
// `?manual=1` in the page's URL stops the clock: window.stride2d.step(n) then advances n frames (what the tests use).
//
// A frame arrives here as gfx2d_internal.h describes it: commands (4 int32 each: kind, first, count, texture), sprite instances (28 bytes) and mesh
// vertices (32 bytes). Both backends below run exactly that, and compute a disc's edge and a texture's lookup the way gfx2d_soft.c does.
// WebGPU cannot be read back at once, so gfx_pixel / gfx_frame_hash see the newest picture that has come back (a frame or more behind); the exact picture
// is `state.readPixels()`, which is asynchronous.

const INSTANCE_BYTES = 28;
const VERTEX_BYTES = 32;
const MAX_SPRITES = 8192;
const MAX_VERTICES = 65536;
const MAX_TEXTURES = 64;
const KIND_SPRITES = 1;
const KIND_TRIANGLES = 2;
const BACKEND_WEBGL2 = 3;
const BACKEND_WEBGPU = 4;

// ---- WebGL2 ---------------------------------------------------------------------------------------------------------------------------
// The same shader text as src/native/gfx2d/gfx2d_gl.c.

const SPRITE_VERT = `#version 300 es
precision highp float;
precision highp int;
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_half;
layout(location = 2) in float a_rot;
layout(location = 3) in vec4 a_color;
layout(location = 4) in uint a_shape;
uniform vec4 u_view;
out vec4 v_color;
out vec2 v_p;
flat out uint v_shape;
void main() {
  vec2 q = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;
  vec2 l = q * a_half;
  float cs = cos(a_rot), sn = sin(a_rot);
  vec2 w = a_pos + vec2(cs * l.x - sn * l.y, sn * l.x + cs * l.y);
  gl_Position = vec4(2.0 * (w - u_view.xy) / (u_view.zw - u_view.xy) - 1.0, 0.0, 1.0);
  v_color = a_color;
  v_p = q;
  v_shape = a_shape;
}`;
const SPRITE_FRAG = `#version 300 es
precision highp float;
in vec4 v_color;
in vec2 v_p;
flat in uint v_shape;
layout(location = 0) out vec4 frag;
void main() {
  float d = length(v_p);
  float w = max(fwidth(d), 0.00001);
  float cover = clamp((1.0 - d) / w + 0.5, 0.0, 1.0);
  if (v_shape == 0u) cover = 1.0;
  frag = vec4(v_color.rgb, v_color.a * cover);
}`;
const MESH_VERT = `#version 300 es
precision highp float;
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in vec4 a_color;
uniform vec4 u_view;
out vec2 v_uv;
out vec4 v_color;
void main() {
  gl_Position = vec4(2.0 * (a_pos - u_view.xy) / (u_view.zw - u_view.xy) - 1.0, 0.0, 1.0);
  v_uv = a_uv;
  v_color = a_color;
}`;
const MESH_FRAG = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
in vec2 v_uv;
in vec4 v_color;
layout(location = 0) out vec4 frag;
void main() {
  frag = texture(u_tex, v_uv) * v_color;
}`;

function makeGfxGL(canvas, memory, log) {
  let gl = null, w = 0, h = 0;
  let spriteProg, meshProg, uSpriteView, uMeshView, uMeshTex, spriteVao, meshVao, instBuf, vertBuf;
  const tex = new Array(MAX_TEXTURES).fill(null);
  const buf = () => memory().buffer;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(vs, fs) {
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }
  // instanced attributes have no base instance in WebGL2: the pointers move instead
  function instancePointers(first) {
    const base = first * INSTANCE_BYTES;
    gl.bindBuffer(gl.ARRAY_BUFFER, instBuf);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, INSTANCE_BYTES, base + 0);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, INSTANCE_BYTES, base + 8);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, INSTANCE_BYTES, base + 16);
    gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, true, INSTANCE_BYTES, base + 20);
    gl.vertexAttribIPointer(4, 1, gl.UNSIGNED_INT, INSTANCE_BYTES, base + 24);
  }

  const imports = {
    gfx_web_init(width, height) {
      try {
        w = width; h = height; canvas.width = w; canvas.height = h;
        gl = canvas.getContext("webgl2", { alpha: false, antialias: false, preserveDrawingBuffer: true });
        if (!gl) return 0;
        spriteProg = program(SPRITE_VERT, SPRITE_FRAG);
        meshProg = program(MESH_VERT, MESH_FRAG);
        uSpriteView = gl.getUniformLocation(spriteProg, "u_view");
        uMeshView = gl.getUniformLocation(meshProg, "u_view");
        uMeshTex = gl.getUniformLocation(meshProg, "u_tex");
        instBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, instBuf);
        gl.bufferData(gl.ARRAY_BUFFER, MAX_SPRITES * INSTANCE_BYTES, gl.DYNAMIC_DRAW);
        vertBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vertBuf);
        gl.bufferData(gl.ARRAY_BUFFER, MAX_VERTICES * VERTEX_BYTES, gl.DYNAMIC_DRAW);
        spriteVao = gl.createVertexArray(); gl.bindVertexArray(spriteVao);
        instancePointers(0);
        for (let i = 0; i < 5; i++) { gl.enableVertexAttribArray(i); gl.vertexAttribDivisor(i, 1); }
        meshVao = gl.createVertexArray(); gl.bindVertexArray(meshVao);
        gl.bindBuffer(gl.ARRAY_BUFFER, vertBuf);
        gl.vertexAttribPointer(0, 2, gl.FLOAT, false, VERTEX_BYTES, 0);
        gl.vertexAttribPointer(1, 2, gl.FLOAT, false, VERTEX_BYTES, 8);
        gl.vertexAttribPointer(2, 4, gl.FLOAT, false, VERTEX_BYTES, 16);
        for (let i = 0; i < 3; i++) gl.enableVertexAttribArray(i);
        gl.bindVertexArray(null);
        gl.enable(gl.BLEND);
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE);
        gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
        return BACKEND_WEBGL2;
      } catch (e) { log("gfx_web_init (webgl2): " + e.message); return 0; }
    },
    gfx_web_shutdown() { gl = null; },
    gfx_web_texture_create(id, tw, th, filter, ptr) {
      const t = gl.createTexture();
      const f = filter === 1 ? gl.LINEAR : gl.NEAREST;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, tw, th, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(buf(), ptr, tw * th * 4));
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, f);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, f);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      tex[id] = { name: t, w: tw, h: th };
    },
    gfx_web_texture_update(id, x, y, rw, rh, ptr) {
      const t = tex[id];
      if (!t) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, t.name);
      gl.pixelStorei(gl.UNPACK_ROW_LENGTH, t.w);       // `ptr` is the whole image: read the rectangle out of it in place
      gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, x);
      gl.pixelStorei(gl.UNPACK_SKIP_ROWS, y);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, x, y, rw, rh, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(buf(), ptr, t.w * t.h * 4));
      gl.pixelStorei(gl.UNPACK_ROW_LENGTH, 0);
      gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, 0);
      gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0);
    },
    gfx_web_texture_free(id) { if (tex[id]) { gl.deleteTexture(tex[id].name); tex[id] = null; } },
    gfx_web_frame(cmdsPtr, ncmds, instPtr, ninst, vertPtr, nverts, l, b, r, t, cr, cg, cb) {
      gl.viewport(0, 0, w, h);
      gl.clearColor(cr, cg, cb, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (ninst > 0) { gl.bindBuffer(gl.ARRAY_BUFFER, instBuf); gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Uint8Array(buf(), instPtr, ninst * INSTANCE_BYTES)); }
      if (nverts > 0) { gl.bindBuffer(gl.ARRAY_BUFFER, vertBuf); gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Uint8Array(buf(), vertPtr, nverts * VERTEX_BYTES)); }
      const cmds = new Int32Array(buf(), cmdsPtr, ncmds * 4);
      for (let c = 0; c < ncmds; c++) {
        const kind = cmds[c * 4], first = cmds[c * 4 + 1], count = cmds[c * 4 + 2], texture = cmds[c * 4 + 3];
        if (kind === KIND_SPRITES) {
          gl.useProgram(spriteProg);
          gl.uniform4f(uSpriteView, l, b, r, t);
          gl.bindVertexArray(spriteVao);
          instancePointers(first);
          gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, count);
        } else if (kind === KIND_TRIANGLES) {
          gl.useProgram(meshProg);
          gl.uniform4f(uMeshView, l, b, r, t);
          gl.uniform1i(uMeshTex, 0);
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, (tex[texture] || tex[0]).name);
          gl.bindVertexArray(meshVao);
          gl.drawArrays(gl.TRIANGLES, first, count);
        }
      }
      gl.bindVertexArray(null);
    },
    gfx_web_read(ptr) { gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(buf(), ptr, w * h * 4)); },
  };
  // the canvas as it was just drawn: RGBA, rows bottom to top (what both backends give)
  const read = async () => { const rgba = new Uint8Array(w * h * 4); gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, rgba); return { w, h, rgba }; };
  return { kind: "webgl2", imports, read };
}

// ---- WebGPU ---------------------------------------------------------------------------------------------------------------------------
// The same picture in WGSL: the same instance and vertex layouts, the same disc edge, straight-alpha blending into the colour and the alpha left alone.

const WGSL = `
struct U { v: vec4f };
@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var tex: texture_2d<f32>;
@group(0) @binding(2) var smp: sampler;

struct SIn {
  @builtin(vertex_index) vi: u32,
  @location(0) pos: vec2f,
  @location(1) hsz: vec2f,
  @location(2) rot: f32,
  @location(3) color: vec4f,
  @location(4) shape: u32,
};
struct SOut {
  @builtin(position) p: vec4f,
  @location(0) color: vec4f,
  @location(1) q: vec2f,
  @location(2) @interpolate(flat) shape: u32,
};
@vertex fn vs_sprite(i: SIn) -> SOut {
  let q = vec2f(f32(i.vi & 1u), f32((i.vi >> 1u) & 1u)) * 2.0 - 1.0;
  let l = q * i.hsz;
  let cs = cos(i.rot);
  let sn = sin(i.rot);
  let w = i.pos + vec2f(cs * l.x - sn * l.y, sn * l.x + cs * l.y);
  var o: SOut;
  o.p = vec4f(2.0 * (w - u.v.xy) / (u.v.zw - u.v.xy) - 1.0, 0.0, 1.0);
  o.color = i.color;
  o.q = q;
  o.shape = i.shape;
  return o;
}
@fragment fn fs_sprite(i: SOut) -> @location(0) vec4f {
  let d = length(i.q);
  let w = max(fwidth(d), 0.00001);
  var cover = clamp((1.0 - d) / w + 0.5, 0.0, 1.0);
  if (i.shape == 0u) { cover = 1.0; }
  return vec4f(i.color.rgb, i.color.a * cover);
}

struct MIn {
  @location(0) pos: vec2f,
  @location(1) uv: vec2f,
  @location(2) color: vec4f,
};
struct MOut {
  @builtin(position) p: vec4f,
  @location(0) uv: vec2f,
  @location(1) color: vec4f,
};
@vertex fn vs_mesh(i: MIn) -> MOut {
  var o: MOut;
  o.p = vec4f(2.0 * (i.pos - u.v.xy) / (u.v.zw - u.v.xy) - 1.0, 0.0, 1.0);
  o.uv = i.uv;
  o.color = i.color;
  return o;
}
@fragment fn fs_mesh(i: MOut) -> @location(0) vec4f {
  return textureSampleLevel(tex, smp, i.uv, 0.0) * i.color;
}`;

// `target` onto the canvas: a pass that loads each pixel (a texture-to-texture copy into the canvas's own texture is not something every implementation takes)
const BLIT = `
@group(0) @binding(0) var src: texture_2d<f32>;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
@fragment fn fs(@builtin(position) p: vec4f) -> @location(0) vec4f { return textureLoad(src, vec2i(p.xy), 0); }`;

// Everything that can fail or must be awaited (adapter, device, pipelines, the canvas's context) happens here, before gfx_web_init, which is synchronous;
// null when this browser has no usable WebGPU (nothing has touched the canvas then, so WebGL2 can still take it).
async function makeGfxGPU(canvas, memory, log) {
  if (!globalThis.navigator || !navigator.gpu) return null;
  let adapter, device, ctx, spritePipe, meshPipe, blitPipe, spriteLayout, meshLayout, blitLayout, instBuf, vertBuf, uniBuf, samplers;
  const FORMAT = "rgba8unorm";
  const blend = {
    color: { srcFactor: "src-alpha", dstFactor: "one-minus-src-alpha", operation: "add" },
    alpha: { srcFactor: "zero", dstFactor: "one", operation: "add" },      // the picture stays opaque
  };
  try {
    adapter = await navigator.gpu.requestAdapter();     // kept in this closure: if it is collected, Chrome tears the whole instance down
    if (!adapter) return null;
    device = await adapter.requestDevice();
    device.lost.then((i) => log("webgpu: device lost: " + i.message));
    device.addEventListener("uncapturederror", (e) => log("webgpu: " + e.error.message));
    const module = device.createShaderModule({ code: WGSL });
    const info = await module.getCompilationInfo();
    for (const m of info.messages) if (m.type === "error") throw new Error("WGSL " + m.lineNum + ": " + m.message);
    spriteLayout = device.createBindGroupLayout({ entries: [{ binding: 0, visibility: GPUShaderStage.VERTEX, buffer: { type: "uniform" } }] });
    meshLayout = device.createBindGroupLayout({ entries: [
      { binding: 0, visibility: GPUShaderStage.VERTEX, buffer: { type: "uniform" } },
      { binding: 1, visibility: GPUShaderStage.FRAGMENT, texture: { sampleType: "float" } },
      { binding: 2, visibility: GPUShaderStage.FRAGMENT, sampler: { type: "filtering" } },
    ] });
    spritePipe = await device.createRenderPipelineAsync({
      layout: device.createPipelineLayout({ bindGroupLayouts: [spriteLayout] }),
      vertex: { module, entryPoint: "vs_sprite", buffers: [{
        arrayStride: INSTANCE_BYTES, stepMode: "instance",
        // GfxInstance, 28 bytes: float x,y | hw,hh | rot | unorm8 r,g,b,a | u32 shape
        attributes: [
          { shaderLocation: 0, offset: 0, format: "float32x2" },
          { shaderLocation: 1, offset: 8, format: "float32x2" },
          { shaderLocation: 2, offset: 16, format: "float32" },
          { shaderLocation: 3, offset: 20, format: "unorm8x4" },
          { shaderLocation: 4, offset: 24, format: "uint32" },
        ] }] },
      fragment: { module, entryPoint: "fs_sprite", targets: [{ format: FORMAT, blend }] },
      primitive: { topology: "triangle-strip" },
    });
    meshPipe = await device.createRenderPipelineAsync({
      layout: device.createPipelineLayout({ bindGroupLayouts: [meshLayout] }),
      vertex: { module, entryPoint: "vs_mesh", buffers: [{
        arrayStride: VERTEX_BYTES, stepMode: "vertex",
        // GfxVertex, 32 bytes: float x,y | u,v | r,g,b,a
        attributes: [
          { shaderLocation: 0, offset: 0, format: "float32x2" },
          { shaderLocation: 1, offset: 8, format: "float32x2" },
          { shaderLocation: 2, offset: 16, format: "float32x4" },
        ] }] },
      fragment: { module, entryPoint: "fs_mesh", targets: [{ format: FORMAT, blend }] },
      primitive: { topology: "triangle-list" },
    });
    const bmod = device.createShaderModule({ code: BLIT });
    blitLayout = device.createBindGroupLayout({ entries: [{ binding: 0, visibility: GPUShaderStage.FRAGMENT, texture: { sampleType: "float" } }] });
    blitPipe = await device.createRenderPipelineAsync({
      layout: device.createPipelineLayout({ bindGroupLayouts: [blitLayout] }),
      vertex: { module: bmod, entryPoint: "vs" }, fragment: { module: bmod, entryPoint: "fs", targets: [{ format: FORMAT }] },
      primitive: { topology: "triangle-list" } });
    samplers = [0, 1].map((f) => device.createSampler({ magFilter: f ? "linear" : "nearest", minFilter: f ? "linear" : "nearest",
                                                         addressModeU: "clamp-to-edge", addressModeV: "clamp-to-edge" }));
    instBuf = device.createBuffer({ size: MAX_SPRITES * INSTANCE_BYTES, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    vertBuf = device.createBuffer({ size: MAX_VERTICES * VERTEX_BYTES, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    uniBuf = device.createBuffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    ctx = canvas.getContext("webgpu");
    if (!ctx) return null;
  } catch (e) { log("webgpu unavailable: " + e.message); return null; }
  // Chrome ends the whole WebGPU instance, and every pending read with it ("A valid external Instance reference no longer exists"), once the objects
  // that own it are collected. A closure variable is not a reliable owner (it can be optimised away), so they are held on the global object for good.
  globalThis.__stride2dGpuKeepAlive = { gpu: navigator.gpu, adapter, device, ctx };

  let w = 0, h = 0, target, spriteBind, blitBind, bpr = 0, stage, cache = null, reading = false, wantRead = false;
  const tex = new Array(MAX_TEXTURES).fill(null);       // { texture, view, filter, w, h, bind }
  const buf = () => memory().buffer;

  // `target` rows copied into a buffer (mapped by the caller), top to bottom -> RGBA, rows bottom to top
  const unpack = (mapped) => {
    const out = new Uint8Array(w * h * 4);
    for (let y = 0; y < h; y++) out.set(mapped.subarray(y * bpr, y * bpr + w * 4), (h - 1 - y) * w * 4);
    return out;
  };
  const copyOut = (enc, b) => enc.copyTextureToBuffer({ texture: target }, { buffer: b, bytesPerRow: bpr }, [w, h]);

  const imports = {
    gfx_web_init(width, height) {
      try {
        w = width; h = height; canvas.width = w; canvas.height = h;
        ctx.configure({ device, format: FORMAT, usage: GPUTextureUsage.RENDER_ATTACHMENT, alphaMode: "opaque" });
        spriteBind = device.createBindGroup({ layout: spriteLayout, entries: [{ binding: 0, resource: { buffer: uniBuf } }] });
        // the picture is drawn into `target`, then blitted to the canvas: so it can be read back at any time (the canvas's own texture expires with the frame)
        target = device.createTexture({ size: [w, h], format: FORMAT, usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_SRC });
        blitBind = device.createBindGroup({ layout: blitLayout, entries: [{ binding: 0, resource: target.createView() }] });
        bpr = Math.ceil(w * 4 / 256) * 256;
        stage = device.createBuffer({ size: bpr * h, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
        return BACKEND_WEBGPU;
      } catch (e) { log("gfx_web_init (webgpu): " + e.message); return 0; }
    },
    gfx_web_shutdown() { wantRead = false; cache = null; },
    gfx_web_texture_create(id, tw, th, filter, ptr) {
      const texture = device.createTexture({ size: [tw, th], format: FORMAT, usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST });
      device.queue.writeTexture({ texture }, new Uint8Array(buf(), ptr, tw * th * 4), { bytesPerRow: tw * 4 }, [tw, th]);
      const view = texture.createView();
      const bind = device.createBindGroup({ layout: meshLayout, entries: [
        { binding: 0, resource: { buffer: uniBuf } }, { binding: 1, resource: view }, { binding: 2, resource: samplers[filter === 1 ? 1 : 0] } ] });
      tex[id] = { texture, w: tw, h: th, bind };
    },
    gfx_web_texture_update(id, x, y, rw, rh, ptr) {
      const t = tex[id];
      if (!t) return;
      // `ptr` is the whole image: the layout's offset and row pitch pick the rectangle out of it
      device.queue.writeTexture({ texture: t.texture, origin: [x, y] }, new Uint8Array(buf(), ptr, t.w * t.h * 4),
                                { offset: (y * t.w + x) * 4, bytesPerRow: t.w * 4 }, [rw, rh]);
    },
    gfx_web_texture_free(id) { if (tex[id]) { tex[id].texture.destroy(); tex[id] = null; } },
    gfx_web_frame(cmdsPtr, ncmds, instPtr, ninst, vertPtr, nverts, l, b, r, t, cr, cg, cb) {
      device.queue.writeBuffer(uniBuf, 0, new Float32Array([l, b, r, t]));
      if (ninst > 0) device.queue.writeBuffer(instBuf, 0, buf(), instPtr, ninst * INSTANCE_BYTES);
      if (nverts > 0) device.queue.writeBuffer(vertBuf, 0, buf(), vertPtr, nverts * VERTEX_BYTES);
      const enc = device.createCommandEncoder();
      const pass = enc.beginRenderPass({ colorAttachments: [{ view: target.createView(), clearValue: { r: cr, g: cg, b: cb, a: 1 }, loadOp: "clear", storeOp: "store" }] });
      const cmds = new Int32Array(buf(), cmdsPtr, ncmds * 4);
      for (let c = 0; c < ncmds; c++) {
        const kind = cmds[c * 4], first = cmds[c * 4 + 1], count = cmds[c * 4 + 2], texture = cmds[c * 4 + 3];
        if (kind === KIND_SPRITES) {
          pass.setPipeline(spritePipe); pass.setBindGroup(0, spriteBind); pass.setVertexBuffer(0, instBuf);
          pass.draw(4, count, 0, first);
        } else if (kind === KIND_TRIANGLES) {
          pass.setPipeline(meshPipe); pass.setBindGroup(0, (tex[texture] || tex[0]).bind); pass.setVertexBuffer(0, vertBuf);
          pass.draw(count, 1, first, 0);
        }
      }
      pass.end();
      const out = enc.beginRenderPass({ colorAttachments: [{ view: ctx.getCurrentTexture().createView(), loadOp: "clear", clearValue: { r: 0, g: 0, b: 0, a: 1 }, storeOp: "store" }] });
      out.setPipeline(blitPipe); out.setBindGroup(0, blitBind); out.draw(3); out.end();
      const grab = wantRead && !reading;
      if (grab) copyOut(enc, stage);
      device.queue.submit([enc.finish()]);
      if (grab) {
        reading = true;
        stage.mapAsync(GPUMapMode.READ).then(() => { cache = unpack(new Uint8Array(stage.getMappedRange())); stage.unmap(); reading = false; }, () => { reading = false; });
      }
    },
    // A synchronous read cannot wait for the GPU. Once a game has asked for pixels (gfx_pixel, gfx_frame_hash) the backend reads each frame back in the
    // background, and this hands over the newest picture that has arrived: a frame or more behind, black until the first one comes.
    gfx_web_read(ptr) {
      wantRead = true;
      const dst = new Uint8Array(buf(), ptr, w * h * 4);
      if (cache) dst.set(cache); else dst.fill(0);
    },
  };
  async function read() {
    const b = device.createBuffer({ size: bpr * h, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
    const enc = device.createCommandEncoder();
    copyOut(enc, b);
    device.queue.submit([enc.finish()]);
    await b.mapAsync(GPUMapMode.READ);
    const rgba = unpack(new Uint8Array(b.getMappedRange()));
    b.unmap(); b.destroy();
    return { w, h, rgba };
  }
  return { kind: "webgpu", imports, read, adapter };
}

// ---- WASI -----------------------------------------------------------------------------------------------------------------------------
// Just what a C program's startup, printf and exit ask for: stdout and stderr go to `log` a line at a time; there is no file system and no environment.

function makeWasi(memory, log, exit) {
  const dec = new TextDecoder();
  let line = "";
  const ENOSYS = 52, EBADF = 8, ENOENT = 44;
  const dv = () => new DataView(memory().buffer);
  const f = {
    fd_write(fd, iovs, n, nwritten) {
      let total = 0;
      for (let i = 0; i < n; i++) {
        const p = dv().getUint32(iovs + i * 8, true), len = dv().getUint32(iovs + i * 8 + 4, true);
        if (fd === 1 || fd === 2) {
          line += dec.decode(new Uint8Array(memory().buffer, p, len), { stream: true });
          let k;
          while ((k = line.indexOf("\n")) >= 0) { log(line.slice(0, k)); line = line.slice(k + 1); }
        }
        total += len;
      }
      dv().setUint32(nwritten, total, true);
      return 0;
    },
    fd_close() { return 0; },
    fd_seek() { return 70; },                              // ESPIPE: the terminals cannot seek
    fd_prestat_get() { return EBADF; },                    // no preopened directories
    fd_prestat_dir_name() { return EBADF; },
    path_open() { return ENOENT; },                        // so fopen simply fails
    // stdout / stderr say they are terminals (a character device that cannot seek), so libc line-buffers them and each line reaches the log when printed
    fd_fdstat_get(fd, buf) {
      if (fd > 2) return EBADF;
      const d = dv();
      d.setUint8(buf, 2); d.setUint8(buf + 1, 0); d.setUint16(buf + 2, 0, true);
      d.setBigUint64(buf + 8, 1n << 6n, true); d.setBigUint64(buf + 16, 0n, true);
      return 0;
    },
    environ_sizes_get(c, s) { dv().setUint32(c, 0, true); dv().setUint32(s, 0, true); return 0; }, environ_get: () => 0,
    args_sizes_get(c, s) { dv().setUint32(c, 0, true); dv().setUint32(s, 0, true); return 0; }, args_get: () => 0,
    clock_time_get(id, prec, out) { dv().setBigUint64(out, BigInt(Math.round(performance.now() * 1e6)), true); return 0; },
    random_get(p, n) { crypto.getRandomValues(new Uint8Array(memory().buffer, p, n)); return 0; },
    proc_exit(code) { exit(code); },
  };
  return new Proxy(f, { get: (t, k) => (k in t ? t[k] : () => ENOSYS) });
}

// ---- the page's entry point ---------------------------------------------------------------------------------------------------------

// ---- input -------------------------------------------------------------------------------------------------------------------------------------------
// The page's events as the five ints gfx2d.h describes ([type, a, b, c, d]; positions in canvas pixels, y from the top), queued here until the module asks
// for them with gfx_web_poll. Keys are named by what they are (event.code), not by the text they make, as in gfx2d.h; the text is its own event.
const KEYS = {
  Escape: 256, Enter: 257, NumpadEnter: 257, Tab: 258, Backspace: 259, Insert: 260, Delete: 261, ArrowRight: 262, ArrowLeft: 263, ArrowDown: 264, ArrowUp: 265,
  PageUp: 266, PageDown: 267, Home: 268, End: 269, ShiftLeft: 340, ControlLeft: 341, AltLeft: 342, MetaLeft: 343, ShiftRight: 344, ControlRight: 345,
  AltRight: 346, MetaRight: 347, Space: 32, Minus: 45, Equal: 61, Comma: 44, Period: 46, Slash: 47, Semicolon: 59, Quote: 39, Backquote: 96,
  BracketLeft: 91, BracketRight: 93, Backslash: 92,
};
function keyOf(e) {
  const c = e.code;
  if (KEYS[c] !== undefined) return KEYS[c];
  let m;
  if ((m = /^Key([A-Z])$/.exec(c))) return m[1].charCodeAt(0);
  if ((m = /^Digit([0-9])$/.exec(c))) return m[1].charCodeAt(0);
  if ((m = /^F([0-9]{1,2})$/.exec(c)) && +m[1] >= 1 && +m[1] <= 12) return 290 + (+m[1]) - 1;
  return 0;
}
function makeInput(canvas, memory) {
  const q = [];
  const mods = (e) => (e.shiftKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.altKey ? 4 : 0) | (e.metaKey ? 8 : 0);
  const pos = (e) => {
    const r = canvas.getBoundingClientRect();
    return [Math.floor((e.clientX - r.left) * canvas.width / r.width), Math.floor((e.clientY - r.top) * canvas.height / r.height)];
  };
  canvas.tabIndex = 0;                                       // so it can have the keyboard
  canvas.style.outline = "none";
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  canvas.addEventListener("pointermove", (e) => { const [x, y] = pos(e); q.push([1, x, y, 0, mods(e)]); });
  canvas.addEventListener("pointerdown", (e) => {
    canvas.focus();
    try { canvas.setPointerCapture(e.pointerId); } catch {}
    const [x, y] = pos(e); q.push([2, x, y, e.button === 1 ? 1 : e.button === 2 ? 2 : 0, mods(e)]);
  });
  canvas.addEventListener("pointerup", (e) => { const [x, y] = pos(e); q.push([3, x, y, e.button === 1 ? 1 : e.button === 2 ? 2 : 0, mods(e)]); });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const k = e.deltaMode === 0 ? 1 / 100 : e.deltaMode === 1 ? 1 / 3 : 1;     // pixels, lines or pages -> notches (a notch is about 100 pixels, 3 lines)
    const [x, y] = pos(e);
    q.push([4, x, y, Math.round(e.deltaX * k * 120), Math.round(-e.deltaY * k * 120)]);
  }, { passive: false });
  canvas.addEventListener("keydown", (e) => {
    const k = keyOf(e);
    if (k) { q.push([5, k, e.repeat ? 1 : 0, 0, mods(e)]); e.preventDefault(); }
    const shortcut = e.metaKey || (e.ctrlKey && !e.altKey);
    if (!shortcut && !e.isComposing && e.key && [...e.key].length === 1) q.push([7, e.key.codePointAt(0), 0, 0, 0]);
  });
  canvas.addEventListener("keyup", (e) => { const k = keyOf(e); if (k) { q.push([6, k, 0, 0, mods(e)]); e.preventDefault(); } });
  canvas.addEventListener("focus", () => q.push([8, 1, 0, 0, 0]));
  canvas.addEventListener("blur", () => q.push([8, 0, 0, 0, 0]));
  return {
    queue: q,
    poll(ptr) {
      const e = q.shift();
      if (!e) return 0;
      new Int32Array(memory().buffer, ptr, 5).set(e);
      return 1;
    },
  };
}

export async function startStride2D({ wasm, canvas, log = console.log, manual = false, gfx = "auto" }) {
  let mem = null;
  const memory = () => mem;
  let backend = null;
  if (gfx === "auto" || gfx === "webgpu") backend = await makeGfxGPU(canvas, memory, log);
  if (!backend && gfx === "webgpu") log("webgpu requested but not available here: using WebGL2");
  if (!backend) backend = makeGfxGL(canvas, memory, log);
  const input = makeInput(canvas, memory);
  const imports = {
    wasi_snapshot_preview1: makeWasi(memory, log, (c) => { throw new Error("exit " + c); }),
    gfx: { ...backend.imports, gfx_web_poll: (ptr) => input.poll(ptr) },
  };
  let instance;
  try {
    ({ instance } = await WebAssembly.instantiateStreaming(fetch(wasm), imports));
  } catch (e) {                                            // a server that does not send application/wasm
    ({ instance } = await WebAssembly.instantiate(await (await fetch(wasm)).arrayBuffer(), imports));
  }
  const x = instance.exports;
  mem = x.memory;
  if (x._initialize) x._initialize();
  const state = { frame: 0, exports: x, error: null, input, backend: backend.kind, readPixels: backend.read, gfx: backend };   // gfx: keeps the WebGPU adapter reachable
  const rc = x.stride2d_init();
  if (rc !== 0) { state.error = "stride2d_init returned " + rc; log(state.error); return state; }
  state.step = (n = 1) => { for (let i = 0; i < n; i++) { x.stride2d_frame(); state.frame++; } return state.frame; };
  if (!manual) {
    let last = performance.now(), acc = 0;
    const STEP = 1000 / 60;
    const tick = (now) => {
      acc += Math.min(now - last, 250); last = now;
      let k = 0;
      while (acc >= STEP && k < 5) { state.step(1); acc -= STEP; k++; }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  return state;
}
