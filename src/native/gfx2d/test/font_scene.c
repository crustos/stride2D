// The font test scene: text drawn with the baked fonts the way a game does (a quad per glyph from gfx_font_glyph, one gfx_triangles call per font). One
// pixel is one world unit (y up), so glyph boxes land on whole pixels. Built into font_test.c (native) and, in place of scene.c, into a WebAssembly page.
#include <stdio.h>
#include <string.h>

#include "../gfx2d.h"

#define W 400
#define H 240

static int put( float* o, int n, float x0, float y0, float x1, float y1, const float* g, float r, float gr, float b, float a )
{
	float u0 = g[0], v0 = g[1], u1 = g[2], v1 = g[3];
	float q[6][8] = { { x0, y0, u0, v1 }, { x1, y0, u1, v1 }, { x1, y1, u1, v0 }, { x0, y0, u0, v1 }, { x1, y1, u1, v0 }, { x0, y1, u0, v0 } };
	int i;
	for ( i = 0; i < 6; i++ )
	{
		float* v = o + ( n + i ) * 8;
		v[0] = q[i][0]; v[1] = q[i][1]; v[2] = q[i][2]; v[3] = q[i][3]; v[4] = r; v[5] = gr; v[6] = b; v[7] = a;
	}
	return n + 6;
}

// draws `s` with the pen at (x, baseline) in font `f`; returns the pen's x afterwards
static float text( int f, float x, float base, const char* s, float r, float g, float b )
{
	static float buf[400 * 6 * 8];
	int n = 0, i;
	for ( i = 0; s[i] && n + 6 <= 400 * 6; i++ )
	{
		float gl[9];
		gfx_font_glyph( f, (unsigned char)s[i], gl );
		if ( gl[4] > 0.f )
			n = put( buf, n, x + gl[6], base + gl[7] - gl[5], x + gl[6] + gl[4], base + gl[7], gl, r, g, b, 1.f );
		x += gl[8];
	}
	gfx_triangles( buf, n, gfx_font_texture( f ) );
	return x;
}

int scene_init( void )
{
	int f;
	float m[4];
	if ( !gfx_init( W, H ) )
		return 0;
	printf( "fonts %d\n", gfx_font_count() );
	for ( f = 0; f < gfx_font_count(); f++ )
	{
		float g[9], a[9];
		gfx_font_metrics( f, m );
		gfx_font_glyph( f, 'A', g );
		gfx_font_glyph( f, 'i', a );
		printf( "font %d size %d tex>0 %d ascent %.0f descent %.0f line %.0f  A w %.0f h %.0f adv %.2f  i adv %.2f  ?-fallback %d\n", f, gfx_font_size( f ),
				gfx_font_texture( f ) > 0, m[0], m[1], m[2], g[4], g[5], g[8], a[8], gfx_font_glyph( f, 0x4e2d, g ) );
	}
	return 1;
}

int scene_frame( int n )
{
	int f;
	float m[4], y = H - 8.f;
	(void)n;
	gfx_camera( W * 0.5f, H * 0.5f, H * 0.5f, 0.12f, 0.14f, 0.2f );
	gfx_begin();
	for ( f = 0; f < gfx_font_count(); f++ )
	{
		gfx_font_metrics( f, m );
		y -= m[0];
		text( f, 8.f, y, "Hello, World! Stride2D 0123 \xe9\xfc\xdf", 1.f, 1.f, 1.f );
		y -= m[1] + 4.f;
	}
	text( 0, 8.f, 12.f, "tint: red", 1.f, 0.4f, 0.4f );
	text( 0, 120.f, 12.f, "green", 0.4f, 1.f, 0.4f );
	return gfx_end();
}
