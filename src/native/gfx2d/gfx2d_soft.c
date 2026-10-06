// gfx2d SOFT backend: a CPU rasteriser. It needs nothing (no GL, no window system, no threads), so a player always has somewhere to draw, and it is
// deterministic, so a game draws the same pixels on every machine.
//
// It is also the REFERENCE the GPU backends are tested against, so it is written from what a frame means (gfx2d.h) and not from the shaders: it maps
// the view to pixels, covers a box where a pixel's centre lies inside it, gives a disc the same one-pixel anti-aliased edge the fragment shaders compute
// (coverage = clamp((1 - d) / width + 0.5), d the distance from the centre in half-sizes, width how much d changes across a pixel), fills triangles with
// the top-left rule so a shared edge is drawn once, and blends straight alpha (source alpha, one minus source alpha). It is not fast and is not meant to be:
// it exists for correctness and as the fallback.
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "gfx2d_internal.h"

typedef struct SoftTex
{
	int used, w, h, filter;
	uint8_t* rgba;
} SoftTex;

static SoftTex g_tex[GFX_MAX_TEXTURES];
static uint8_t* g_fb; // rows bottom to top, RGBA
static int g_w, g_h;

static float clamp01( float v )
{
	return v < 0.f ? 0.f : ( v > 1.f ? 1.f : v );
}

// sinf and cosf are only accurate to within a unit in the last place, and which last bit a C library picks differs between libraries (glibc, musl, the one a
// .NET runtime calls), so a rotated sprite could land a pixel differently on each. In double precision the libraries agree to far more digits than a float
// keeps, so the float they round to is the same everywhere. (sqrt, floor, and the rest of the arithmetic here are exactly rounded by IEEE 754 already, and
// the build keeps the compiler from fusing multiply-adds.)
static float sin_det( float x )
{
	return (float)sin( (double)x );
}

static float cos_det( float x )
{
	return (float)cos( (double)x );
}

static uint8_t to_u8( float v ) // v in 0..1
{
	return (uint8_t)( clamp01( v ) * 255.f + 0.5f );
}

// dst = src * a + dst * (1 - a), on straight colours in 0..1; the picture's alpha stays 255
static void blend( uint8_t* dst, float r, float g, float b, float a )
{
	float inv = 1.f - a;
	dst[0] = to_u8( r * a + ( dst[0] * ( 1.f / 255.f ) ) * inv );
	dst[1] = to_u8( g * a + ( dst[1] * ( 1.f / 255.f ) ) * inv );
	dst[2] = to_u8( b * a + ( dst[2] * ( 1.f / 255.f ) ) * inv );
}

// ---- sprites ------------------------------------------------------------------------------------------------------------------------

static void draw_sprite( const GfxFrame* f, const GfxInstance* s )
{
	float sx = (float)f->width / ( f->right - f->left );
	float sy = (float)f->height / ( f->top - f->bottom );
	float hw = fabsf( s->hw ), hh = fabsf( s->hh );
	float cs, sn, ex, ey;
	int x0, x1, y0, y1, px, py;
	float r, g, b, a;

	if ( hw < 1e-9f || hh < 1e-9f )
		return;
	cs = cos_det( s->rot );
	sn = sin_det( s->rot );
	ex = fabsf( cs ) * hw + fabsf( sn ) * hh; // half extent of the turned box, world units
	ey = fabsf( sn ) * hw + fabsf( cs ) * hh;
	x0 = (int)floorf( ( s->x - ex - f->left ) * sx );
	x1 = (int)ceilf( ( s->x + ex - f->left ) * sx );
	y0 = (int)floorf( ( s->y - ey - f->bottom ) * sy );
	y1 = (int)ceilf( ( s->y + ey - f->bottom ) * sy );
	if ( x0 < 0 )
		x0 = 0;
	if ( y0 < 0 )
		y0 = 0;
	if ( x1 > f->width - 1 )
		x1 = f->width - 1;
	if ( y1 > f->height - 1 )
		y1 = f->height - 1;
	r = (float)( s->rgba & 255u ) * ( 1.f / 255.f );
	g = (float)( ( s->rgba >> 8 ) & 255u ) * ( 1.f / 255.f );
	b = (float)( ( s->rgba >> 16 ) & 255u ) * ( 1.f / 255.f );
	a = (float)( ( s->rgba >> 24 ) & 255u ) * ( 1.f / 255.f );

	for ( py = y0; py <= y1; py++ )
	{
		for ( px = x0; px <= x1; px++ )
		{
			// the pixel's centre in the sprite's own space: -1..1 across the box
			float wx = f->left + ( (float)px + 0.5f ) / sx;
			float wy = f->bottom + ( (float)py + 0.5f ) / sy;
			float dx = wx - s->x, dy = wy - s->y;
			float lx = ( cs * dx + sn * dy ) / hw;
			float ly = ( -sn * dx + cs * dy ) / hh;
			float cov = 1.f;
			if ( !( fabsf( lx ) <= 1.f && fabsf( ly ) <= 1.f ) )
				continue;
			if ( s->shape == GFX_SHAPE_DISC )
			{
				// d at this pixel and one pixel over in x and in y: how fast d changes is the width of the anti-aliased edge (fwidth)
				float d = sqrtf( lx * lx + ly * ly );
				float lx1 = ( cs * ( dx + 1.f / sx ) + sn * dy ) / hw, ly1 = ( -sn * ( dx + 1.f / sx ) + cs * dy ) / hh;
				float lx2 = ( cs * dx + sn * ( dy + 1.f / sy ) ) / hw, ly2 = ( -sn * dx + cs * ( dy + 1.f / sy ) ) / hh;
				float w = fabsf( sqrtf( lx1 * lx1 + ly1 * ly1 ) - d ) + fabsf( sqrtf( lx2 * lx2 + ly2 * ly2 ) - d );
				if ( w < 1e-5f )
					w = 1e-5f;
				cov = clamp01( ( 1.f - d ) / w + 0.5f );
			}
			blend( &g_fb[( (size_t)py * (size_t)f->width + (size_t)px ) * 4], r, g, b, a * cov );
		}
	}
}

// ---- triangles ----------------------------------------------------------------------------------------------------------------------

static void sample( const SoftTex* t, float u, float v, float out[4] )
{
	int i;
	if ( t->filter == GFX_FILTER_LINEAR )
	{
		float fx = u * (float)t->w - 0.5f, fy = v * (float)t->h - 0.5f;
		int ix = (int)floorf( fx ), iy = (int)floorf( fy );
		float tx = fx - (float)ix, ty = fy - (float)iy;
		int xs[2], ys[2];
		xs[0] = ix < 0 ? 0 : ( ix > t->w - 1 ? t->w - 1 : ix );
		xs[1] = ix + 1 < 0 ? 0 : ( ix + 1 > t->w - 1 ? t->w - 1 : ix + 1 );
		ys[0] = iy < 0 ? 0 : ( iy > t->h - 1 ? t->h - 1 : iy );
		ys[1] = iy + 1 < 0 ? 0 : ( iy + 1 > t->h - 1 ? t->h - 1 : iy + 1 );
		for ( i = 0; i < 4; i++ )
		{
			float c00 = t->rgba[( (size_t)ys[0] * (size_t)t->w + (size_t)xs[0] ) * 4 + i];
			float c10 = t->rgba[( (size_t)ys[0] * (size_t)t->w + (size_t)xs[1] ) * 4 + i];
			float c01 = t->rgba[( (size_t)ys[1] * (size_t)t->w + (size_t)xs[0] ) * 4 + i];
			float c11 = t->rgba[( (size_t)ys[1] * (size_t)t->w + (size_t)xs[1] ) * 4 + i];
			float top = c00 + ( c10 - c00 ) * tx, bot = c01 + ( c11 - c01 ) * tx;
			out[i] = ( top + ( bot - top ) * ty ) * ( 1.f / 255.f );
		}
	}
	else
	{
		int ix = (int)floorf( u * (float)t->w ), iy = (int)floorf( v * (float)t->h );
		const uint8_t* p;
		ix = ix < 0 ? 0 : ( ix > t->w - 1 ? t->w - 1 : ix );
		iy = iy < 0 ? 0 : ( iy > t->h - 1 ? t->h - 1 : iy );
		p = &t->rgba[( (size_t)iy * (size_t)t->w + (size_t)ix ) * 4];
		for ( i = 0; i < 4; i++ )
			out[i] = (float)p[i] * ( 1.f / 255.f );
	}
}

// Edge function of the directed edge a -> b at p: positive to the left of it (inside, for a counter-clockwise triangle in a y-up space).
static float edge( float ax, float ay, float bx, float by, float px, float py )
{
	return ( bx - ax ) * ( py - ay ) - ( by - ay ) * ( px - ax );
}

// A pixel centre exactly on an edge belongs to the triangle only if the edge is a left edge (it goes down) or a top edge (horizontal, going left):
// then two triangles that share an edge draw each pixel on it once.
static int owns_edge( float ax, float ay, float bx, float by )
{
	float dx = bx - ax, dy = by - ay;
	return dy < 0.f || ( dy == 0.f && dx < 0.f );
}

static void draw_triangle( const GfxFrame* f, const GfxVertex* a, const GfxVertex* b, const GfxVertex* c, const SoftTex* t )
{
	float sx = (float)f->width / ( f->right - f->left );
	float sy = (float)f->height / ( f->top - f->bottom );
	float ax = ( a->x - f->left ) * sx, ay = ( a->y - f->bottom ) * sy;
	float bx = ( b->x - f->left ) * sx, by = ( b->y - f->bottom ) * sy;
	float cx = ( c->x - f->left ) * sx, cy = ( c->y - f->bottom ) * sy;
	float area = edge( ax, ay, bx, by, cx, cy );
	float minx, maxx, miny, maxy;
	int x0, x1, y0, y1, px, py;
	int own0, own1, own2;
	const GfxVertex* tmp;

	if ( area == 0.f || area != area )
		return;
	if ( area < 0.f ) // the other winding: swap two corners so the inside is where all three edge functions are positive
	{
		float sw;
		sw = bx; bx = cx; cx = sw;
		sw = by; by = cy; cy = sw;
		tmp = b; b = c; c = tmp;
		area = -area;
	}
	minx = fminf( ax, fminf( bx, cx ) );
	maxx = fmaxf( ax, fmaxf( bx, cx ) );
	miny = fminf( ay, fminf( by, cy ) );
	maxy = fmaxf( ay, fmaxf( by, cy ) );
	x0 = (int)floorf( minx );
	x1 = (int)ceilf( maxx );
	y0 = (int)floorf( miny );
	y1 = (int)ceilf( maxy );
	if ( x0 < 0 )
		x0 = 0;
	if ( y0 < 0 )
		y0 = 0;
	if ( x1 > f->width - 1 )
		x1 = f->width - 1;
	if ( y1 > f->height - 1 )
		y1 = f->height - 1;
	own0 = owns_edge( bx, by, cx, cy ); // the edge opposite a
	own1 = owns_edge( cx, cy, ax, ay ); // opposite b
	own2 = owns_edge( ax, ay, bx, by ); // opposite c

	for ( py = y0; py <= y1; py++ )
	{
		for ( px = x0; px <= x1; px++ )
		{
			float x = (float)px + 0.5f, y = (float)py + 0.5f;
			float w0 = edge( bx, by, cx, cy, x, y );
			float w1 = edge( cx, cy, ax, ay, x, y );
			float w2 = edge( ax, ay, bx, by, x, y );
			float l0, l1, l2, u, v, r, g, bl, al, texel[4];
			if ( w0 < 0.f || w1 < 0.f || w2 < 0.f )
				continue;
			if ( ( w0 == 0.f && !own0 ) || ( w1 == 0.f && !own1 ) || ( w2 == 0.f && !own2 ) )
				continue;
			l0 = w0 / area;
			l1 = w1 / area;
			l2 = w2 / area;
			u = l0 * a->u + l1 * b->u + l2 * c->u;
			v = l0 * a->v + l1 * b->v + l2 * c->v;
			r = l0 * a->r + l1 * b->r + l2 * c->r;
			g = l0 * a->g + l1 * b->g + l2 * c->g;
			bl = l0 * a->b + l1 * b->b + l2 * c->b;
			al = l0 * a->a + l1 * b->a + l2 * c->a;
			sample( t, u, v, texel );
			blend( &g_fb[( (size_t)py * (size_t)f->width + (size_t)px ) * 4], texel[0] * r, texel[1] * g, texel[2] * bl, texel[3] * al );
		}
	}
}

// ---- the backend --------------------------------------------------------------------------------------------------------------------

static int soft_init( int width, int height )
{
	g_fb = (uint8_t*)calloc( (size_t)width * (size_t)height, 4 );
	if ( g_fb == NULL )
		return 0;
	g_w = width;
	g_h = height;
	memset( g_tex, 0, sizeof g_tex );
	return 1;
}

static void soft_shutdown( void )
{
	int i;
	for ( i = 0; i < GFX_MAX_TEXTURES; i++ )
		free( g_tex[i].rgba );
	memset( g_tex, 0, sizeof g_tex );
	free( g_fb );
	g_fb = NULL;
}

static int soft_windowed( void )
{
	return 0;
}

static void soft_texture_create( int id, int width, int height, int filter, const uint8_t* rgba )
{
	size_t bytes = (size_t)width * (size_t)height * 4;
	free( g_tex[id].rgba );
	g_tex[id].rgba = (uint8_t*)malloc( bytes );
	if ( g_tex[id].rgba == NULL )
	{
		g_tex[id].used = 0;
		return;
	}
	memcpy( g_tex[id].rgba, rgba, bytes );
	g_tex[id].used = 1;
	g_tex[id].w = width;
	g_tex[id].h = height;
	g_tex[id].filter = filter;
}

static void soft_texture_update( int id, int x, int y, int w, int h, const uint8_t* image )
{
	int row;
	if ( !g_tex[id].used )
		return;
	for ( row = y; row < y + h; row++ )
	{
		size_t at = ( (size_t)row * (size_t)g_tex[id].w + (size_t)x ) * 4;
		memcpy( g_tex[id].rgba + at, image + at, (size_t)w * 4 );
	}
}

static void soft_texture_free( int id )
{
	free( g_tex[id].rgba );
	g_tex[id].rgba = NULL;
	g_tex[id].used = 0;
}

static void soft_frame( const GfxFrame* f )
{
	size_t i, n = (size_t)f->width * (size_t)f->height;
	uint8_t cr = to_u8( f->bg_r ), cg = to_u8( f->bg_g ), cb = to_u8( f->bg_b );
	int c;
	for ( i = 0; i < n; i++ )
	{
		g_fb[i * 4] = cr;
		g_fb[i * 4 + 1] = cg;
		g_fb[i * 4 + 2] = cb;
		g_fb[i * 4 + 3] = 255;
	}
	for ( c = 0; c < f->ncmds; c++ )
	{
		const GfxCmd* cmd = &f->cmds[c];
		int k;
		if ( cmd->kind == GFXCMD_SPRITES )
		{
			for ( k = 0; k < cmd->count; k++ )
				draw_sprite( f, &f->inst[cmd->first + k] );
		}
		else if ( cmd->kind == GFXCMD_TRIANGLES )
		{
			const SoftTex* t = g_tex[cmd->texture].used ? &g_tex[cmd->texture] : &g_tex[0];
			for ( k = 0; k + 2 < cmd->count; k += 3 )
				draw_triangle( f, &f->verts[cmd->first + k], &f->verts[cmd->first + k + 1], &f->verts[cmd->first + k + 2], t );
		}
	}
}

static int soft_present( void )
{
	return 1;
}

static void soft_read( uint8_t* rgba )
{
	memcpy( rgba, g_fb, (size_t)g_w * (size_t)g_h * 4 );
}

const GfxBackend gfx_backend_soft = {
	"soft", GFX_BACKEND_SOFT, soft_init, soft_shutdown, soft_windowed, soft_texture_create, soft_texture_update, soft_texture_free, soft_frame, soft_present, soft_read,
};
