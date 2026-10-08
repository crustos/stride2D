// The light scene: the bars of the fx2 scene (16 bars, upper half (i/15, .5, 1-i/15), lower half grey i/15; 400 x 240) lit by
//   x 0..200, all rows      three point lights over a blue-ish ambient (smooth falloff, glow 0.2)
//   x 200..400, rows 0..120 one point light (linear falloff) centred in the cell
//   x 200..400, rows 120..240 a spot light pointing down from the cell's top edge (quadratic falloff)
// tools/gfx_test.py works out each pixel from the light formulas written out again in Python.
#include <math.h>
#include <stdio.h>

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

static void clip( int x, int y, int w, int h )
{
	if ( gfx_clip( x, y, w, h ) != 1 )
		g_api_fail++;
}

int scene_frame( int n )
{
	float bars[32 * 12];
	// lights: ambient (0), falloff (4), glow (5), then light 1: x y radius intensity (6..9) color (12), light 2 (16..19, 20), light 3 (24..27, 28)
	float lights[32] = { [0] = 0.2f, 0.25f, 0.4f, 1.f, [4] = 1.f, 0.2f,
		[6] = 0.25f, 0.35f, 0.3f, 1.2f, [12] = 1.f, 0.8f, 0.5f, 1.f,
		[16] = 0.15f, 0.75f, 0.25f, 1.f, [20] = 0.4f, 0.7f, 1.f, 1.f,
		[24] = 0.4f, 0.6f, 0.2f, 0.8f, [28] = 1.f, 0.4f, 0.6f, 1.f };
	float one[32] = { [0] = 0.1f, 0.1f, 0.1f, 1.f, [4] = 0.f, 0.f,
		[6] = 0.75f, 0.25f, 0.3f, 1.f, [12] = 1.f, 1.f, 1.f, 1.f, [19] = 0.f, [27] = 0.f }; // lights 2 and 3 off
	// spot light: ambient (0), x y direction cone softness reach intensity falloff (4..11), color (12), glow (16)
	float spot[17] = { [0] = 0.1f, 0.1f, 0.15f, 1.f, [4] = 0.75f, 0.5f, -90.f, 30.f, 0.4f, 0.45f, 1.5f, 2.f, [12] = 1.f, 0.95f, 0.8f, 1.f, [16] = 0.1f };
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
	clip( 0, 0, 200, 240 );
	if ( gfx_effect( GFX_FX_LIGHTS, lights, 28 + 4 ) != 1 ) g_api_fail++;
	clip( 200, 0, 200, 120 );
	if ( gfx_effect( GFX_FX_LIGHTS, one, 32 ) != 1 ) g_api_fail++;
	clip( 200, 120, 200, 120 );
	if ( gfx_effect( GFX_FX_SPOT_LIGHT, spot, 17 ) != 1 ) g_api_fail++;
	if ( gfx_clip_reset() != 1 )
		g_api_fail++;
	return gfx_end();
}
