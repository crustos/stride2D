// gfx2d internals: what the shared core (gfx2d_core.c) hands to a backend. Not part of the API; nothing outside src/native/gfx2d includes this.
//
// A frame is described ONCE, here, in the form a GPU wants: a list of draw commands, the sprite instances and the mesh vertices they point into, and the
// view. Every backend (gfx2d_soft.c, gfx2d_gl.c, gfx2d_web.c + stride2d_web.js) only executes that description, so the things that must agree between them
// (the layer order, the colour rounding, the view, what a command means) are written in one place, in C.
#ifndef STRIDE2D_GFX2D_INTERNAL_H
#define STRIDE2D_GFX2D_INTERNAL_H

#include <stdint.h>

#include "gfx2d.h"

// One sprite, as it goes to the GPU (28 bytes: 5 floats, the tint as 4 bytes, the shape). The layer is gone: the core has already put the
// instances in drawing order.
typedef struct GfxInstance
{
	float x, y;			 // centre, world units
	float hw, hh;		 // half size, world units
	float rot;			 // radians
	uint32_t rgba;		 // r | g << 8 | b << 16 | a << 24 (the bytes in memory are r, g, b, a: what an unorm8x4 attribute reads)
	uint32_t shape;		 // GFX_SHAPE_*
} GfxInstance;

// One mesh vertex (32 bytes): exactly a record of a mesh batch, so the core copies it as it is.
typedef struct GfxVertex
{
	float x, y, u, v, r, g, b, a;
} GfxVertex;

#define GFXCMD_SPRITES 1   // draw instances [first, first + count)
#define GFXCMD_TRIANGLES 2 // draw vertices [first, first + count) with `texture`
#define GFXCMD_CLIP 3      // later draws only change pixels in a rectangle, in pixels from the TOP left, end exclusive: first = x0 | y0 << 16, count = x1 | y1 << 16
                           // (0 <= x0 <= x1 <= width, likewise y); the whole picture is the state at the start of every frame
#define GFXCMD_EFFECT 4    // an effect pass over the picture so far, inside the clip in force: first = the effect's id (GFX_FX_*), count = its slot in GfxFrame.fx

typedef struct GfxCmd
{
	int32_t kind, first, count, texture;
} GfxCmd;

#define GFX_MAX_CMDS 1024
#define GFX_INSTANCE_BYTES ( (int)sizeof( GfxInstance ) )
#define GFX_VERTEX_BYTES ( (int)sizeof( GfxVertex ) )

typedef struct GfxFrame
{
	int width, height;
	float left, bottom, right, top; // the view, world units (y up)
	float bg_r, bg_g, bg_b;
	const GfxCmd* cmds;
	int ncmds;
	const GfxInstance* inst;
	int ninst;
	const GfxVertex* verts;
	int nverts;
	const float* fx; // nfx slots of GFX_FX_PARAMS floats: the parameters of the frame's effects, already complete (the core has filled in the defaults)
	int nfx;
} GfxFrame;

// A backend. Every picture is width x height, RGBA8, and `read` gives it with its rows BOTTOM TO TOP (what glReadPixels gives); alpha is 255 everywhere.
typedef struct GfxBackend
{
	const char* name;
	int id;											// GFX_BACKEND_*
	int ( *init )( int width, int height );			// 1 if it can draw; 0 leaves nothing behind
	void ( *shutdown )( void );
	int ( *windowed )( void );						// 1 if present shows the frame in a window or page
	// Textures are made and changed with the whole image in hand. id 0 is made by the core at init (1x1 white).
	void ( *texture_create )( int id, int width, int height, int filter, const uint8_t* rgba );
	void ( *texture_update )( int id, int x, int y, int w, int h, const uint8_t* image ); // `image` is the whole image; only (x, y, w, h) of it is new
	void ( *texture_free )( int id );
	void ( *frame )( const GfxFrame* f );			// clear to the background, then run the commands
	int ( *present )( void );						// shows the frame; 1 while the game should go on, 0 once the window is closed
	void ( *read )( uint8_t* rgba );				// the last frame
	void ( *poll )( void );							// may be NULL: takes what the window or page has received and gfx_input_push()es it
} GfxBackend;

// For a backend: queue an input event (the five ints of gfx_poll_event). Returns 0 if the queue is full.
int gfx_input_push( int type, int a, int b, int c, int d );
// For a backend: the window was closed.
void gfx_input_close( void );

// Backends. Which of them exist in a build is a compile-time choice (GFX_HAVE_SOFT, GFX_HAVE_GL, GFX_HAVE_WEB).
extern const GfxBackend gfx_backend_soft;
extern const GfxBackend gfx_backend_gl;
extern GfxBackend gfx_backend_web; // not const: its `id` says WEBGL2 or WEBGPU, which the page's script decides at init

#endif
