// gfx2d WEB backend: gfx2d.h for WebAssembly in a page. This file only hands the frame description (gfx2d_internal.h) to JavaScript; the drawing, with
// WebGPU when the browser has it and WebGL2 when not, is web/stride2d_web.js. The module imports these functions from the "gfx" namespace, which the
// page's script provides:
//
//     int  gfx_web_init(int w, int h)       3 (WebGL2) or 4 (WebGPU), the GFX_BACKEND_* the script drew with; 0 if the page can do neither
//     void gfx_web_shutdown(void)
//     void gfx_web_texture_create(int id, int w, int h, int filter, const void* rgba)
//     void gfx_web_texture_update(int id, int x, int y, int w, int h, const void* image)      `image` is the whole image; the script knows its width
//     void gfx_web_texture_free(int id)
//     void gfx_web_frame(const void* cmds, int ncmds, const void* inst, int ninst, const void* verts, int nverts,
//                        float left, float bottom, float right, float top, float bg_r, float bg_g, float bg_b, const void* fx, int nfx)
//                                           `fx` is nfx slots of GFX_FX_PARAMS floats: the parameters of the frame's effects (GFXCMD_EFFECT says which slot)
//     int  gfx_web_poll(int* out5)          the oldest input event the page has received, as the five ints of gfx_poll_event; 0 if there is none
//     void gfx_web_read(void* rgba)         the canvas as just drawn, RGBA, rows bottom to top. WebGPU cannot be read at once: it gives the newest
//                                           picture that has come back from the GPU, a frame or more behind (black until the first)
//
// There is no file system on a page, so gfx_save_frame writes nothing (it returns 0). The picture is read back only when something asks for it
// (gfx_pixel, gfx_frame_hash), so a game that only draws pays nothing for it.
#include <stdint.h>

#include "gfx2d_internal.h"

#define WEB_IMPORT( name ) __attribute__( ( import_module( "gfx" ), import_name( #name ) ) )

WEB_IMPORT( gfx_web_init ) int gfx_web_init( int w, int h );
WEB_IMPORT( gfx_web_shutdown ) void gfx_web_shutdown( void );
WEB_IMPORT( gfx_web_texture_create ) void gfx_web_texture_create( int id, int w, int h, int filter, const void* rgba );
WEB_IMPORT( gfx_web_texture_update ) void gfx_web_texture_update( int id, int x, int y, int w, int h, const void* image );
WEB_IMPORT( gfx_web_texture_free ) void gfx_web_texture_free( int id );
WEB_IMPORT( gfx_web_frame )
void gfx_web_frame( const void* cmds, int ncmds, const void* inst, int ninst, const void* verts, int nverts, float l, float b, float r, float t, float cr,
					float cg, float cb, const void* fx, int nfx );
WEB_IMPORT( gfx_web_read ) void gfx_web_read( void* rgba );
WEB_IMPORT( gfx_web_poll ) int gfx_web_poll( int* out5 );

static int web_init( int width, int height )
{
	int kind = gfx_web_init( width, height );
	if ( kind != GFX_BACKEND_WEBGL2 && kind != GFX_BACKEND_WEBGPU )
		return 0;
	gfx_backend_web.id = kind;
	return 1;
}

static void web_shutdown( void )
{
	gfx_web_shutdown();
}

static int web_windowed( void )
{
	return 1;
}

static void web_texture_create( int id, int w, int h, int filter, const uint8_t* rgba )
{
	gfx_web_texture_create( id, w, h, filter, rgba );
}

static void web_texture_update( int id, int x, int y, int w, int h, const uint8_t* image )
{
	gfx_web_texture_update( id, x, y, w, h, image );
}

static void web_texture_free( int id )
{
	gfx_web_texture_free( id );
}

static void web_frame( const GfxFrame* f )
{
	gfx_web_frame( f->cmds, f->ncmds, f->inst, f->ninst, f->verts, f->nverts, f->left, f->bottom, f->right, f->top, f->bg_r, f->bg_g, f->bg_b, f->fx, f->nfx );
}

static int web_present( void )
{
	return 1; // the browser shows the canvas by itself
}

static void web_read( uint8_t* rgba )
{
	gfx_web_read( rgba );
}

static void web_poll( void )
{
	int e[5], n = 0;
	while ( n++ < GFX_MAX_EVENTS && gfx_web_poll( e ) )
		gfx_input_push( e[0], e[1], e[2], e[3], e[4] );
}

GfxBackend gfx_backend_web = {
	"web", GFX_BACKEND_WEBGL2, web_init, web_shutdown, web_windowed, web_texture_create, web_texture_update, web_texture_free, web_frame, web_present, web_read,
	web_poll,
};
