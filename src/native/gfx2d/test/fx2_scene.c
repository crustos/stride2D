// The second effect scene: the effects ported from OpenToonz (blend, HSV / HLS adjust, levels, gradients), one in each cell of a 4 x 4 grid of 100 x 60 pixel cells
// (a cell is a clip), over bars: 16 bars, 25 pixels wide, each (i/15, 0.5, 1 - i/15) in the upper half (rows 0..119) and a grey i/15 in the lower half.
//
//   row 0   blend: multiply | overlay (alpha .8, opacity .75) | soft light | darker color
//   row 1   HSV adjust | HLS adjust (cylindrical) | HLS adjust (conical) | levels
//   row 2   levels per channel | linear gradient | radial gradient | square gradient
//   row 3   diamond gradient | spin gradient | four points gradient | linear gradient with a wave
//
// tools/gfx_test.py computes what each cell must hold from the OpenToonz formulas, written out again in Python.
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "../gfx2d.h"

#define W 400
#define H 240

static int g_api_fail;

static void box( float* o, float x, float y, float hw, float hh, float r, float g, float b )
{
	o[0] = x; o[1] = y; o[2] = hw; o[3] = hh; o[4] = 0.f;
	o[5] = r; o[6] = g; o[7] = b; o[8] = 1.f;
	o[9] = 0.f; o[10] = 0.f; o[11] = 0.f;
}

int fx_scene_api_failures( void )
{
	return g_api_fail;
}

int scene_init( void )
{
	return gfx_init( W, H );
}

// the cell (c, r): clip it, and say where its middle is as the fractions the effects take
static void cell( int c, int r, float* cx, float* cy )
{
	if ( gfx_clip( 100 * c, 60 * r, 100, 60 ) != 1 )
		g_api_fail++;
	*cx = (float)( 100 * c + 50 ) / (float)W;
	*cy = (float)( 60 * r + 30 ) / (float)H;
}

static void fx( int id, const float* p, int n )
{
	if ( gfx_effect( id, p, n ) != 1 )
		g_api_fail++;
}

int scene_frame( int n )
{
	float bars[32 * 12];
	float cx, cy;
	int i;
	(void)n;
	g_api_fail = 0;
	gfx_camera( W * 0.5f, H * 0.5f, H * 0.5f, 0.12f, 0.14f, 0.2f );
	gfx_begin();
	for ( i = 0; i < 16; i++ )
	{
		float t = (float)i / 15.f;
		box( &bars[i * 12], 12.5f + 25.f * (float)i, 180.f, 12.5f, 60.f, t, 0.5f, 1.f - t );
		box( &bars[( 16 + i ) * 12], 12.5f + 25.f * (float)i, 60.f, 12.5f, 60.f, t, t, t );
	}
	gfx_sprites( bars, 32 );

	{ // blend: the parameters are mode, (pad), color r g b a at 4, opacity at 8
		float a[9] = { 1, 0, 0, 0, 1.f, 0.5f, 0.1f, 1.f, 1.f };
		float b[9] = { 12, 0, 0, 0, 0.3f, 0.6f, 0.9f, 0.8f, 0.75f };
		float c[9] = { 13, 0, 0, 0, 0.7f, 0.4f, 0.2f, 1.f, 1.f };
		float d[9] = { 6, 0, 0, 0, 0.5f, 0.5f, 0.5f, 1.f, 1.f };
		cell( 0, 0, &cx, &cy ); fx( GFX_FX_BLEND, a, 9 );
		cell( 1, 0, &cx, &cy ); fx( GFX_FX_BLEND, b, 9 );
		cell( 2, 0, &cx, &cy ); fx( GFX_FX_BLEND, c, 9 );
		cell( 3, 0, &cx, &cy ); fx( GFX_FX_BLEND, d, 9 );
	}
	{ // hsv: hue pivot, scale, shift, value pivot, scale, shift, saturation pivot, scale, shift
		float h[9] = { 0, 1, 40, 0, 1, -0.1f, 0, 1.5f, 0 };
		// hls: hue pivot, scale, shift, lightness pivot, scale, shift, saturation pivot, scale, shift, cylindrical
		float l1[10] = { 0, 1, -60, 0, 0.8f, 0, 0, 1.3f, 0, 1 };
		float l2[10] = { 120, 0.5f, 0, 0, 1, 0.1f, 0, 1, 0, 0 };
		// levels: in low, in high, gamma, out low, out high, clamp
		float lv[6] = { 0.1f, 0.9f, 1.8f, 0.05f, 0.95f, 1 };
		cell( 0, 1, &cx, &cy ); fx( GFX_FX_HSV_ADJUST, h, 9 );
		cell( 1, 1, &cx, &cy ); fx( GFX_FX_HLS_ADJUST, l1, 10 );
		cell( 2, 1, &cx, &cy ); fx( GFX_FX_HLS_ADJUST, l2, 10 );
		cell( 3, 1, &cx, &cy ); fx( GFX_FX_LEVELS, lv, 6 );
	}
	{ // levels per channel: five numbers for red, five for green, five for blue, then clamp
		float rgb[16] = { 0.2f, 0.8f, 1, 0, 1,   0, 1, 2.2f, 0, 1,   0, 1, 1, 0.1f, 0.6f,   1 };
		// linear gradient: center x, y, angle, period, wave amplitude, frequency, phase, offset, color 1 (8), color 2 (12), curve, opacity
		float lin[18] = { 0, 0, 30, 120, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 1 };
		// radial gradient: center x, y, outer radius, inner radius, color 1 (4), color 2 (8), curve, opacity
		float rad[14] = { 0, 0, 45, 10, 1, 1, 1, 1, 0, 0, 0.5f, 0.5f, 2, 1 };
		// square / diamond gradient: center x, y, size, (pad), color 1 (4), color 2 (8), opacity (12)
		float sq[13] = { 0, 0, 60, 0, 1, 1, 1, 1, 0, 0, 0, 1, 1 };
		cell( 0, 2, &cx, &cy ); fx( GFX_FX_LEVELS_RGB, rgb, 16 );
		cell( 1, 2, &cx, &cy ); lin[0] = cx; lin[1] = cy; fx( GFX_FX_LINEAR_GRADIENT, lin, 18 );
		cell( 2, 2, &cx, &cy ); rad[0] = cx; rad[1] = cy; fx( GFX_FX_RADIAL_GRADIENT, rad, 14 );
		cell( 3, 2, &cx, &cy ); sq[0] = cx; sq[1] = cy; fx( GFX_FX_SQUARE_GRADIENT, sq, 13 );
	}
	{
		float dia[13] = { 0, 0, 30, 0, 1, 1, 1, 1, 0, 0, 0, 1, 1 };
		// spin gradient: center x, y, start angle, end angle, color 1 (4), color 2 (8), curve, opacity
		float spin[14] = { 0, 0, 45, 270, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1 };
		// four points: x, y for each of four points, then four colors (8, 12, 16, 20), opacity (24)
		float four[25] = { 0.9f, 0.1f, 0.1f, 0.1f, 0.1f, 0.9f, 0.9f, 0.9f,
			1, 0, 0, 1,  0, 1, 0, 1,  0, 0, 1, 1,  1, 1, 0, 1,  1 };
		float wave[18] = { 0, 0, 90, 80, 8, 0.2f, 0.5f, 0, 1, 0.8f, 0, 1, 0, 0.3f, 1, 1, 0, 1 };
		int k;
		cell( 0, 3, &cx, &cy ); dia[0] = cx; dia[1] = cy; fx( GFX_FX_DIAMOND_GRADIENT, dia, 13 );
		cell( 1, 3, &cx, &cy ); spin[0] = cx; spin[1] = cy; fx( GFX_FX_SPIN_GRADIENT, spin, 14 );
		cell( 2, 3, &cx, &cy );
		for ( k = 0; k < 4; k++ ) // the points of the cell, as fractions of the picture
		{
			four[2 * k] = ( 200.f + ( four[2 * k] > 0.5f ? 90.f : 10.f ) ) / (float)W;
			four[2 * k + 1] = ( 180.f + ( four[2 * k + 1] > 0.5f ? 50.f : 10.f ) ) / (float)H;
		}
		fx( GFX_FX_FOUR_POINTS_GRADIENT, four, 25 );
		cell( 3, 3, &cx, &cy ); wave[0] = cx; wave[1] = cy; fx( GFX_FX_LINEAR_GRADIENT, wave, 18 );
	}
	if ( gfx_clip_reset() != 1 )
		g_api_fail++;
	return gfx_end();
}
