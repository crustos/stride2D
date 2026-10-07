// gfx2d core: the API of gfx2d.h, everything that is the same whichever backend draws. See gfx2d_internal.h for what a backend is handed.
//
// What is decided here, once: the order sprites are drawn in (a stable sort by layer), how a tint becomes bytes, the view, which texture ids exist,
// what a frame can hold, and how the last picture is read back and hashed. A backend then only draws a description of the frame.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gfx2d_font.h"
#include "gfx2d_internal.h"

// ---- state --------------------------------------------------------------------------------------------------------------------------

static int g_events[GFX_MAX_EVENTS][5];
static int g_ev_head, g_ev_count, g_ev_dropped;

static const GfxBackend* g_be;
static int g_ready;
static int g_w, g_h;
static int g_running = 1;
static int g_open;		  // a frame has begun and not yet ended
static int g_have_frame;  // gfx_end has run at least once
static int g_stale;		  // g_pixels is older than the last frame

static float g_cx, g_cy, g_half = 5.f;
static float g_bgr, g_bgg, g_bgb;

static GfxInstance g_inst[GFX_MAX_SPRITES];
static int g_ninst;
static GfxVertex g_verts[GFX_MAX_VERTICES];
static int g_nverts;
static GfxCmd g_cmds[GFX_MAX_CMDS];
static int g_ncmds;
static int g_clip[4]; // x0, y0, x1, y1: the clip the commands so far have left in force

typedef struct TexInfo
{
	int used, w, h, filter;
} TexInfo;
static TexInfo g_tex[GFX_MAX_TEXTURES]; // [0] is the white texel

static uint8_t* g_pixels; // the last frame, rows bottom to top, for gfx_pixel / gfx_frame_hash / gfx_save_frame

// stats of the last finished frame
static int g_st_calls, g_st_sprites, g_st_vertices, g_st_bytes, g_st_frames;

// ---- small helpers ------------------------------------------------------------------------------------------------------------------

// A tint as a byte: round to nearest, clamped. (Not lrintf: its result depends on the rounding mode, this does not.)
static uint32_t to_byte( float v )
{
	if ( !( v > 0.f ) ) // also catches NaN
		return 0;
	if ( v >= 1.f )
		return 255;
	return (uint32_t)( v * 255.f + 0.5f );
}

static int layer_of( float f )
{
	if ( !( f >= 0.f ) )
		return 0;
	if ( f >= 255.f )
		return 255;
	return (int)f;
}

static void open_frame( void )
{
	if ( g_open )
		return;
	g_open = 1;
	g_ninst = g_nverts = g_ncmds = 0;
	g_clip[0] = g_clip[1] = 0;
	g_clip[2] = g_w;
	g_clip[3] = g_h;
}

// ---- backends ------------------------------------------------------------------------------------------------------------------------

#if defined( GFX_HAVE_GL ) || defined( GFX_HAVE_SOFT )
static int wants( const char* want, const char* name )
{
	return want == NULL || want[0] == 0 || strcmp( want, "auto" ) == 0 || strcmp( want, name ) == 0;
}
#endif

int gfx_init( int width, int height )
{
	const GfxBackend* list[3];
	int n = 0, i;

	if ( g_ready || width < 1 || height < 1 || width > GFX_MAX_SIZE || height > GFX_MAX_SIZE )
		return 0;
#ifdef GFX_HAVE_WEB
	list[n++] = &gfx_backend_web; // a page has one way to draw; the script picks WebGPU or WebGL2
#endif
#if defined( GFX_HAVE_GL ) || defined( GFX_HAVE_SOFT )
	{
		const char* want = getenv( "STRIDE2D_GFX" ); // "gl" or "soft" force one; anything else (or nothing) is the best there is
#ifdef GFX_HAVE_GL
		if ( wants( want, "gl" ) )
			list[n++] = &gfx_backend_gl;
#endif
#ifdef GFX_HAVE_SOFT
		if ( wants( want, "soft" ) )
			list[n++] = &gfx_backend_soft;
#endif
	}
#endif
	g_be = NULL;
	for ( i = 0; i < n; i++ )
	{
		if ( list[i]->init( width, height ) )
		{
			g_be = list[i];
			break;
		}
	}
	if ( g_be == NULL )
		return 0;

	g_pixels = (uint8_t*)calloc( (size_t)width * (size_t)height, 4 );
	if ( g_pixels == NULL )
	{
		g_be->shutdown();
		g_be = NULL;
		return 0;
	}
	g_w = width;
	g_h = height;
	memset( g_tex, 0, sizeof g_tex );
	{
		static const uint8_t white[4] = { 255, 255, 255, 255 };
		g_tex[0].used = 1;
		g_tex[0].w = g_tex[0].h = 1;
		g_tex[0].filter = GFX_FILTER_NEAREST;
		g_be->texture_create( 0, 1, 1, GFX_FILTER_NEAREST, white );
	}
	g_open = g_have_frame = g_stale = 0;
	g_ninst = g_nverts = g_ncmds = 0;
	g_running = 1;
	g_ev_head = g_ev_count = g_ev_dropped = 0;
	g_st_calls = g_st_sprites = g_st_vertices = g_st_bytes = g_st_frames = 0;
	g_ready = 1;
	return 1;
}

void gfx_shutdown( void )
{
	int i;
	if ( !g_ready )
		return;
	for ( i = 1; i < GFX_MAX_TEXTURES; i++ )
		if ( g_tex[i].used )
			g_be->texture_free( i );
	g_be->texture_free( 0 );
	gfx_font_reset();
	g_be->shutdown();
	free( g_pixels );
	g_pixels = NULL;
	g_be = NULL;
	g_ready = 0;
}

int gfx_backend( void )
{
	return g_ready ? g_be->id : GFX_BACKEND_NONE;
}

void gfx_camera( float centerX, float centerY, float halfHeight, float r, float g, float b )
{
	g_cx = centerX;
	g_cy = centerY;
	g_half = halfHeight;
	g_bgr = r;
	g_bgg = g;
	g_bgb = b;
}

// ---- textures -----------------------------------------------------------------------------------------------------------------------

int gfx_texture( int width, int height, int filter, const uint8_t* rgba )
{
	int id;
	uint8_t* zeros = NULL;
	if ( !g_ready || width < 1 || height < 1 || width > GFX_MAX_SIZE || height > GFX_MAX_SIZE )
		return 0;
	for ( id = 1; id < GFX_MAX_TEXTURES && g_tex[id].used; id++ )
		;
	if ( id >= GFX_MAX_TEXTURES )
		return 0;
	if ( rgba == NULL )
	{
		zeros = (uint8_t*)calloc( (size_t)width * (size_t)height, 4 );
		if ( zeros == NULL )
			return 0;
		rgba = zeros;
	}
	g_tex[id].used = 1;
	g_tex[id].w = width;
	g_tex[id].h = height;
	g_tex[id].filter = filter == GFX_FILTER_LINEAR ? GFX_FILTER_LINEAR : GFX_FILTER_NEAREST;
	g_be->texture_create( id, width, height, g_tex[id].filter, rgba );
	free( zeros );
	return id;
}

void gfx_texture_update( int id, int x, int y, int width, int height, const uint8_t* rgba )
{
	int x1, y1;
	if ( !g_ready || rgba == NULL || id < 1 || id >= GFX_MAX_TEXTURES || !g_tex[id].used )
		return;
	x1 = x + width;
	y1 = y + height;
	if ( x < 0 )
		x = 0;
	if ( y < 0 )
		y = 0;
	if ( x1 > g_tex[id].w )
		x1 = g_tex[id].w;
	if ( y1 > g_tex[id].h )
		y1 = g_tex[id].h;
	if ( x1 <= x || y1 <= y )
		return;
	g_be->texture_update( id, x, y, x1 - x, y1 - y, rgba );
}

void gfx_texture_free( int id )
{
	if ( !g_ready || id < 1 || id >= GFX_MAX_TEXTURES || !g_tex[id].used )
		return;
	g_be->texture_free( id );
	g_tex[id].used = 0;
}

// ---- a frame ------------------------------------------------------------------------------------------------------------------------

void gfx_begin( void )
{
	if ( !g_ready )
		return;
	g_open = 0; // a second gfx_begin throws away what the first one collected
	open_frame();
}

int gfx_sprites( const float* sprites, int count )
{
	static int order[GFX_MAX_SPRITES];
	static int start[257];
	int i, room;
	GfxCmd* cmd;

	if ( !g_ready )
		return 0;
	open_frame();
	if ( sprites == NULL || count <= 0 || g_ncmds >= GFX_MAX_CMDS )
		return 0;
	room = GFX_MAX_SPRITES - g_ninst;
	if ( count > room )
		count = room;
	if ( count <= 0 )
		return 0;

	// a stable counting sort by layer: equal layers keep the order the game gave them
	memset( start, 0, sizeof start );
	for ( i = 0; i < count; i++ )
		start[layer_of( sprites[i * GFX_SPRITE_FLOATS + 10] ) + 1]++;
	for ( i = 0; i < 256; i++ )
		start[i + 1] += start[i];
	for ( i = 0; i < count; i++ )
		order[start[layer_of( sprites[i * GFX_SPRITE_FLOATS + 10] )]++] = i;

	cmd = &g_cmds[g_ncmds++];
	cmd->kind = GFXCMD_SPRITES;
	cmd->first = g_ninst;
	cmd->count = count;
	cmd->texture = 0;
	for ( i = 0; i < count; i++ )
	{
		const float* s = &sprites[order[i] * GFX_SPRITE_FLOATS];
		GfxInstance* o = &g_inst[g_ninst++];
		o->x = s[0];
		o->y = s[1];
		o->hw = s[2];
		o->hh = s[3];
		o->rot = s[4];
		o->rgba = to_byte( s[5] ) | ( to_byte( s[6] ) << 8 ) | ( to_byte( s[7] ) << 16 ) | ( to_byte( s[8] ) << 24 );
		o->shape = s[9] > 0.5f ? GFX_SHAPE_DISC : GFX_SHAPE_BOX;
	}
	return count;
}

int gfx_triangles( const float* vertices, int count, int texture )
{
	int room;
	GfxCmd* cmd;
	if ( !g_ready )
		return 0;
	open_frame();
	if ( vertices == NULL || count < 3 || g_ncmds >= GFX_MAX_CMDS )
		return 0;
	room = GFX_MAX_VERTICES - g_nverts;
	if ( count > room )
		count = room;
	count -= count % 3;
	if ( count <= 0 )
		return 0;
	if ( texture < 0 || texture >= GFX_MAX_TEXTURES || !g_tex[texture].used )
		texture = 0;
	memcpy( &g_verts[g_nverts], vertices, (size_t)count * sizeof( GfxVertex ) );
	cmd = &g_cmds[g_ncmds++];
	cmd->kind = GFXCMD_TRIANGLES;
	cmd->first = g_nverts;
	cmd->count = count;
	cmd->texture = texture;
	g_nverts += count;
	return count;
}

int gfx_clip( int x, int y, int width, int height )
{
	int x0, y0, x1, y1;
	GfxCmd* cmd;
	if ( !g_ready )
		return 0;
	open_frame();
	// the rectangle is cut to the picture; one with nothing in it (or none of it on the picture) hides everything that follows
	x0 = x < 0 ? 0 : ( x > g_w ? g_w : x );
	y0 = y < 0 ? 0 : ( y > g_h ? g_h : y );
	x1 = width <= 0 ? x0 : ( (long long)x + width > g_w ? g_w : x + width );
	y1 = height <= 0 ? y0 : ( (long long)y + height > g_h ? g_h : y + height );
	if ( x1 < x0 )
		x1 = x0;
	if ( y1 < y0 )
		y1 = y0;
	if ( x0 == g_clip[0] && y0 == g_clip[1] && x1 == g_clip[2] && y1 == g_clip[3] )
		return 1;
	if ( g_ncmds >= GFX_MAX_CMDS )
		return 0;
	cmd = &g_cmds[g_ncmds++];
	cmd->kind = GFXCMD_CLIP;
	cmd->first = x0 | ( y0 << 16 );
	cmd->count = x1 | ( y1 << 16 );
	cmd->texture = 0;
	g_clip[0] = x0;
	g_clip[1] = y0;
	g_clip[2] = x1;
	g_clip[3] = y1;
	return 1;
}

int gfx_clip_reset( void )
{
	return gfx_clip( 0, 0, g_w, g_h );
}

int gfx_end( void )
{
	GfxFrame f;
	float half_w, half_h;
	int i;
	if ( !g_ready )
		return 0;
	open_frame(); // a frame with nothing in it still clears the picture
	half_h = g_half > 0.0001f ? g_half : 0.0001f;
	half_w = half_h * ( (float)g_w / (float)g_h );
	f.width = g_w;
	f.height = g_h;
	f.left = g_cx - half_w;
	f.right = g_cx + half_w;
	f.bottom = g_cy - half_h;
	f.top = g_cy + half_h;
	f.bg_r = g_bgr;
	f.bg_g = g_bgg;
	f.bg_b = g_bgb;
	f.cmds = g_cmds;
	f.ncmds = g_ncmds;
	f.inst = g_inst;
	f.ninst = g_ninst;
	f.verts = g_verts;
	f.nverts = g_nverts;
	g_be->frame( &f );
	g_running = g_be->present();

	g_st_calls = 0;
	for ( i = 0; i < g_ncmds; i++ )
		if ( g_cmds[i].kind != GFXCMD_CLIP )
			g_st_calls++;
	g_st_sprites = g_ninst;
	g_st_vertices = g_nverts;
	g_st_bytes = g_ninst * GFX_INSTANCE_BYTES + g_nverts * GFX_VERTEX_BYTES;
	g_st_frames++;
	g_open = 0;
	g_have_frame = 1;
	g_stale = 1;
	return g_running;
}

int gfx_draw( const float* sprites, int count )
{
	int n;
	if ( !g_ready )
		return 0;
	gfx_begin();
	n = gfx_sprites( sprites, count );
	gfx_end();
	return n;
}

// ---- the picture --------------------------------------------------------------------------------------------------------------------

static int sync_pixels( void )
{
	if ( !g_ready || !g_have_frame )
		return 0;
	if ( g_stale )
	{
		g_be->read( g_pixels );
		g_stale = 0;
	}
	return 1;
}

uint32_t gfx_pixel( int x, int y )
{
	const uint8_t* p;
	if ( !g_ready || x < 0 || y < 0 || x >= g_w || y >= g_h || !sync_pixels() )
		return 0;
	p = &g_pixels[( (size_t)( g_h - 1 - y ) * (size_t)g_w + (size_t)x ) * 4]; // the buffer's rows run bottom to top
	return ( (uint32_t)p[3] << 24 ) | ( (uint32_t)p[0] << 16 ) | ( (uint32_t)p[1] << 8 ) | (uint32_t)p[2];
}

int gfx_frame_hash( void )
{
	uint32_t h = 2166136261u; // FNV-1a over the rows as they are stored
	size_t i, n = (size_t)g_w * (size_t)g_h * 4;
	if ( !sync_pixels() )
		return 0;
	for ( i = 0; i < n; i++ )
		h = ( h ^ g_pixels[i] ) * 16777619u;
	return (int)h;
}

int gfx_save_frame( int index )
{
	char path[64];
	FILE* f;
	int x, y;
	if ( !sync_pixels() )
		return 0;
	snprintf( path, sizeof path, "frame_%04d.ppm", index );
	f = fopen( path, "wb" );
	if ( f == NULL )
		return 0;
	fprintf( f, "P6\n%d %d\n255\n", g_w, g_h );
	for ( y = g_h - 1; y >= 0; y-- )
	{
		for ( x = 0; x < g_w; x++ )
		{
			const uint8_t* p = &g_pixels[( (size_t)y * (size_t)g_w + (size_t)x ) * 4];
			fputc( p[0], f );
			fputc( p[1], f );
			fputc( p[2], f );
		}
	}
	fclose( f );
	return 1;
}

int gfx_stat( int which )
{
	switch ( which )
	{
		case GFX_STAT_DRAW_CALLS: return g_st_calls;
		case GFX_STAT_SPRITES: return g_st_sprites;
		case GFX_STAT_VERTICES: return g_st_vertices;
		case GFX_STAT_BYTES_UPLOADED: return g_st_bytes;
		case GFX_STAT_WINDOWED: return g_ready && g_be->windowed() ? 1 : 0;
		case GFX_STAT_FRAMES: return g_st_frames;
		case GFX_STAT_EVENTS_DROPPED: return g_ev_dropped;
		default: return 0;
	}
}

// ---- input --------------------------------------------------------------------------------------------------------------------------------

int gfx_input_push( int type, int a, int b, int c, int d )
{
	int* e;
	if ( g_ev_count >= GFX_MAX_EVENTS )
	{
		g_ev_dropped++;
		return 0;
	}
	e = g_events[( g_ev_head + g_ev_count ) % GFX_MAX_EVENTS];
	e[0] = type;
	e[1] = a;
	e[2] = b;
	e[3] = c;
	e[4] = d;
	g_ev_count++;
	return 1;
}

void gfx_input_close( void )
{
	g_running = 0;
	gfx_input_push( GFX_EVENT_CLOSE, 0, 0, 0, 0 );
}

int gfx_poll_event( int* out5 )
{
	if ( !g_ready || out5 == NULL )
		return 0;
	if ( g_ev_count == 0 && g_be->poll != NULL )
		g_be->poll();
	if ( g_ev_count == 0 )
		return 0;
	memcpy( out5, g_events[g_ev_head], 5 * sizeof( int ) );
	g_ev_head = ( g_ev_head + 1 ) % GFX_MAX_EVENTS;
	g_ev_count--;
	return 1;
}

int gfx_inject_event( int type, int a, int b, int c, int d )
{
	if ( !g_ready || type < GFX_EVENT_MOUSE_MOVE || type > GFX_EVENT_CLOSE )
		return 0;
	return gfx_input_push( type, a, b, c, d );
}
