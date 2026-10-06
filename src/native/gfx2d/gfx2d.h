// gfx2d: the 2D renderer of Stride2D, as a small C library with no dependency on .NET.
//
// It draws what the engine already produces: the sprite batch (Renderer2D.DrawData: boxes and discs) and the mesh triangle list
// (Renderer2D.MeshData: the pieces of a shattered sprite, any convex polygon), plus textures for the meshes. One API, four backends:
//
//   GL      desktop OpenGL ES 3 through EGL, loaded at run time (no GL, EGL or X11 development files are needed to build, and a machine without
//           them still runs: see SOFT). A window opens when there is an X11 display; otherwise it draws offscreen (EGL surfaceless).
//   SOFT    a CPU rasteriser. Needs nothing, runs anywhere, and is deterministic: the same game draws the same pixels on every machine, which
//           makes it the fallback when there is no GL and the reference the GPU backends are tested against.
//   WEBGL2  in a browser, WebAssembly calling WebGL2 through src/native/gfx2d/web/stride2d_web.js.
//   WEBGPU  the same page, drawing with WebGPU when the browser has it.
//
// A native player picks GL, or SOFT when GL is not there (STRIDE2D_GFX=soft or =gl overrides that). A wasm player built for a page picks
// WEBGPU or WEBGL2 in the page's script. Everything else is the same C, so a batch means the same thing on all of them.
//
// This header is the only place the API is written down: tools/gen_pb2.py --lib gfx2d reads it, from the markers below, and writes the C#
// bindings (class GFX: a .NET flavor with [LibraryImport], and the C flavor the C# -> C translator compiles against). Every pointer parameter says
// what it is: GFX_IN_ARR (an array the callee reads).
#ifndef STRIDE2D_GFX2D_H
#define STRIDE2D_GFX2D_H

#include <stdint.h>

#if defined( _WIN32 )
#define GFX_API __declspec( dllexport )
#else
#define GFX_API __attribute__( ( visibility( "default" ) ) )
#endif

#define GFX_IN
#define GFX_OUT
#define GFX_IN_ARR
#define GFX_OUT_ARR

#ifdef __cplusplus
extern "C" {
#endif

// ---- the batches --------------------------------------------------------------------------------------------------------------------
//
// A SPRITE BATCH is `count` records of GFX_SPRITE_FLOATS floats, in this order (what Renderer2D.Collect writes):
//    x, y            the centre, in world units
//    halfW, halfH    half the size, in world units
//    angle           radians, counter-clockwise
//    r, g, b, a      the tint, 0..1
//    shape           GFX_SHAPE_BOX, or GFX_SHAPE_DISC (an ellipse when halfW and halfH differ; its edge is anti-aliased into its alpha)
//    layer           0..255: a higher layer draws over a lower one; equal layers draw in the order given
//    (one float spare)
// A MESH BATCH is `count` vertices of GFX_MESH_VERTEX_FLOATS floats, drawn as a triangle list in world space (what Renderer2D.CollectMeshes writes):
//    x, y            the position, in world units
//    u, v            the texture coordinate: 0..1 over the whole image, v = 0 at the image's FIRST row of data
//    r, g, b, a      the tint, 0..1, multiplied with the texel
#define GFX_SPRITE_FLOATS 12
#define GFX_MESH_VERTEX_FLOATS 8

// What one frame can hold. A draw that does not fit is cut short, and says how many it drew.
#define GFX_MAX_SPRITES 8192
#define GFX_MAX_VERTICES 65536
#define GFX_MAX_TEXTURES 64 // ids 0 (the white texel) to 63
#define GFX_MAX_SIZE 8192

#define GFX_SHAPE_BOX 0
#define GFX_SHAPE_DISC 1

#define GFX_FILTER_NEAREST 0
#define GFX_FILTER_LINEAR 1

// gfx_backend()
#define GFX_BACKEND_NONE 0
#define GFX_BACKEND_SOFT 1
#define GFX_BACKEND_GL 2
#define GFX_BACKEND_WEBGL2 3
#define GFX_BACKEND_WEBGPU 4

// gfx_stat()
#define GFX_STAT_DRAW_CALLS 0       // draw calls the last frame made
#define GFX_STAT_SPRITES 1          // sprites it drew
#define GFX_STAT_VERTICES 2         // mesh vertices it drew
#define GFX_STAT_BYTES_UPLOADED 3   // bytes of draw data it sent to the backend
#define GFX_STAT_WINDOWED 4         // 1 if the frame goes to a window (GL with a display, or a page), 0 if it is only kept in memory
#define GFX_STAT_FRAMES 5           // frames finished since gfx_init
#define GFX_STAT_EVENTS_DROPPED 6   // input events lost because the queue (GFX_MAX_EVENTS) was full, since gfx_init

// ---- input ----------------------------------------------------------------------------------------------------------------------------
//
// What the window, or the page, receives is queued and read with gfx_poll_event: five ints, [type, a, b, c, d]. Positions are in picture pixels, x from the
// left and y from the TOP (the way a UI lays itself out), whatever the backend. The queue holds GFX_MAX_EVENTS; a full queue drops the NEW event.
//
//   type                 a            b           c               d
//   GFX_EVENT_MOUSE_MOVE x            y           0               mods
//   GFX_EVENT_MOUSE_DOWN x            y           button          mods       button: GFX_BUTTON_LEFT / MIDDLE / RIGHT
//   GFX_EVENT_MOUSE_UP   x            y           button          mods
//   GFX_EVENT_WHEEL      x            y           dx              dy         in 1/120 of a notch: dy > 0 scrolls up (away from the user), dx > 0 right
//   GFX_EVENT_KEY_DOWN   key          repeat      0               mods       key: a GFX_KEY_*; repeat is 1 for an auto-repeat
//   GFX_EVENT_KEY_UP     key          0           0               mods
//   GFX_EVENT_TEXT       codepoint    0           0               0          a typed character (Unicode); the window gives Latin-1, the page any character
//   GFX_EVENT_FOCUS      1 or 0       0           0               0          the window or page gained or lost the keyboard
//   GFX_EVENT_CLOSE      0            0           0               0          the window was closed (gfx_end then returns 0 as well)
// A key's `key` is its ASCII code for a printable key (letters as the capital: 'A'), and the GFX_KEY_* below for the others, whatever the layout's text.
#define GFX_MAX_EVENTS 256

#define GFX_EVENT_NONE 0
#define GFX_EVENT_MOUSE_MOVE 1
#define GFX_EVENT_MOUSE_DOWN 2
#define GFX_EVENT_MOUSE_UP 3
#define GFX_EVENT_WHEEL 4
#define GFX_EVENT_KEY_DOWN 5
#define GFX_EVENT_KEY_UP 6
#define GFX_EVENT_TEXT 7
#define GFX_EVENT_FOCUS 8
#define GFX_EVENT_CLOSE 9

#define GFX_BUTTON_LEFT 0
#define GFX_BUTTON_MIDDLE 1
#define GFX_BUTTON_RIGHT 2

#define GFX_MOD_SHIFT 1
#define GFX_MOD_CTRL 2
#define GFX_MOD_ALT 4
#define GFX_MOD_SUPER 8

#define GFX_KEY_ESCAPE 256
#define GFX_KEY_ENTER 257
#define GFX_KEY_TAB 258
#define GFX_KEY_BACKSPACE 259
#define GFX_KEY_INSERT 260
#define GFX_KEY_DELETE 261
#define GFX_KEY_RIGHT 262
#define GFX_KEY_LEFT 263
#define GFX_KEY_DOWN 264
#define GFX_KEY_UP 265
#define GFX_KEY_PAGE_UP 266
#define GFX_KEY_PAGE_DOWN 267
#define GFX_KEY_HOME 268
#define GFX_KEY_END 269
#define GFX_KEY_F1 290 // F1..F12 are 290..301
#define GFX_KEY_LEFT_SHIFT 340
#define GFX_KEY_LEFT_CTRL 341
#define GFX_KEY_LEFT_ALT 342
#define GFX_KEY_LEFT_SUPER 343
#define GFX_KEY_RIGHT_SHIFT 344
#define GFX_KEY_RIGHT_CTRL 345
#define GFX_KEY_RIGHT_ALT 346
#define GFX_KEY_RIGHT_SUPER 347

// ---- the renderer -------------------------------------------------------------------------------------------------------------------

// Opens the renderer with a width x height picture. Returns 1, or 0 if it cannot (nothing else may then be called). It tries the best backend
// the machine has and falls back to SOFT, so on a desktop it fails only for a size outside 1..GFX_MAX_SIZE.
GFX_API int gfx_init( int width, int height );
GFX_API void gfx_shutdown( void );

// Which backend is drawing (GFX_BACKEND_*), and 0 before gfx_init.
GFX_API int gfx_backend( void );

// The view: the world point at the centre, half the visible height in world units (the width follows the picture's aspect), the background colour.
GFX_API void gfx_camera( float centerX, float centerY, float halfHeight, float r, float g, float b );

// ---- textures: for meshes. Texture 0 is a plain white texel and always exists. ----------------------------------------------------------
//
// An image is width x height pixels of 4 bytes (r, g, b, a: straight alpha), row by row, the first row first; `rgba` must hold width * height * 4 bytes
// (a null array makes a transparent image). gfx_texture returns an id of 1 or more, or 0 if the size is wrong or all the ids are in use.
GFX_API int gfx_texture( int width, int height, int filter, GFX_IN_ARR const uint8_t *rgba );

// Sends the rectangle (x, y, width, height) of `rgba` to the texture: `rgba` is the WHOLE image again (the size the texture was made with), of which only
// that rectangle is read. This is what destructible terrain does with its dirty rectangle: GFX.TextureUpdate(id, x0, y0, w, h, layer.Pixels).
GFX_API void gfx_texture_update( int id, int x, int y, int width, int height, GFX_IN_ARR const uint8_t *rgba );
GFX_API void gfx_texture_free( int id );

// ---- a frame --------------------------------------------------------------------------------------------------------------------------
//
// gfx_begin clears to the background colour. gfx_sprites and gfx_triangles then draw in the order they are called (so a game decides what is in front:
// within one call, sprites go by layer). gfx_end finishes the frame: it shows it in the window, if there is one, and returns 1 while the game should
// go on (0 once the window has been closed; always 1 without a window). A draw before gfx_begin starts the frame by itself.
GFX_API void gfx_begin( void );

// Draws a sprite batch; returns how many sprites it drew.
GFX_API int gfx_sprites( GFX_IN_ARR const float *sprites, int count );

// Draws `count` mesh vertices (a multiple of 3) with a texture (0: white); returns how many vertices it drew.
GFX_API int gfx_triangles( GFX_IN_ARR const float *vertices, int count, int texture );

GFX_API int gfx_end( void );

// A frame of sprites only: gfx_begin, gfx_sprites, gfx_end. Returns how many sprites it drew.
GFX_API int gfx_draw( GFX_IN_ARR const float *sprites, int count );

// ---- the picture ----------------------------------------------------------------------------------------------------------------------
//
// The last finished frame: one pixel as 0xAARRGGBB (x from the left, y from the TOP), a hash of the whole frame (the same pixels always give the same
// hash), and a file, frame_NNNN.ppm in the current directory (gfx_save_frame returns 1 if it was written). A page cannot read the GPU at once, so on
// WEBGPU these give the newest picture that has come back from it, a frame or more behind (the page's own script has an exact, asynchronous read).
GFX_API uint32_t gfx_pixel( int x, int y );
GFX_API int gfx_frame_hash( void );
GFX_API int gfx_save_frame( int index );

GFX_API int gfx_stat( int which );

// ---- input: reading ---------------------------------------------------------------------------------------------------------------------
//
// Writes the oldest queued event to out5 (five ints, above) and returns 1, or returns 0 with out5 untouched when there is none. It first lets the window or
// the page deliver what it has received, so it works between frames; a game normally drains it once a frame.
GFX_API int gfx_poll_event( GFX_OUT_ARR int *out5 );

// Queues an event as if it had come from the window: what a test or a scripted demo uses, the same on every backend. Returns 1, or 0 if the queue was full
// (and counts it in GFX_STAT_EVENTS_DROPPED). An unknown type or one before gfx_init is refused (0).
GFX_API int gfx_inject_event( int type, int a, int b, int c, int d );

#ifdef __cplusplus
}
#endif

#endif
