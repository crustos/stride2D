// The effect test scene: a ramp of colored bars over a ramp of greys, then effects applied to different parts of it, to see that every backend gives the same pixels
// where an effect runs and leaves the rest alone. 400 x 240; one pixel is one world unit (y up) and a clip counts pixels from the TOP.
//
//   x   0..100  brightness / contrast (0.1, 0.15), over the full height
//       100..200 tint (orange, 0.6)
//       200..300 two effects, one after the other: brightness / contrast (-0.3, -0.5), then tint (blue, 0.5): the second sees the first's result
//       300..350 brightness / contrast with a NaN brightness (the default, 0, is used) and contrast -0.4, rows 40..140 only
//       350..400 tint with no parameters at all (the defaults), rows 40..140 only
//   and an effect inside an EMPTY clip (changes nothing), and a white disc drawn AFTER the effects (an effect changes only what was drawn before it).
//
// The bars are 25 pixels wide: bar i (0..15) is (i/15, 0.5, 1 - i/15) in the upper band (rows 20..110) and a grey i/15 in the lower one (rows 130..220).
// tools/gfx_test.py computes what each effect should give from these numbers.
#include <math.h>
#include <stdio.h>

#include "../gfx2d.h"

#define W 400
#define H 240

static int g_api_fail;

static void box( float* o, float x, float y, float hw, float hh, float r, float g, float b, int shape )
{
	o[0] = x; o[1] = y; o[2] = hw; o[3] = hh; o[4] = 0.f;
	o[5] = r; o[6] = g; o[7] = b; o[8] = 1.f;
	o[9] = (float)shape; o[10] = 0.f; o[11] = 0.f;
}

static void check( int ok )
{
	if ( !ok )
		g_api_fail++;
}

// How many of the API's refusals did not come out as they should (the native driver prints it)
int fx_scene_api_failures( void )
{
	return g_api_fail;
}

int scene_init( void )
{
	return gfx_init( W, H );
}

int scene_frame( int n )
{
	float bars[32 * 12], disc[12];
	float bc_a[2] = { 0.1f, 0.15f }, tint_b[5] = { 1.f, 0.5f, 0.1f, 1.f, 0.6f };
	float bc_c[2] = { -0.3f, -0.5f }, tint_c[5] = { 0.2f, 0.4f, 1.f, 1.f, 0.5f };
	float bc_d[2] = { NAN, -0.4f }, bc_hidden[2] = { 1.f, 1.f };
	int i;
	(void)n;
	g_api_fail = 0;
	gfx_camera( W * 0.5f, H * 0.5f, H * 0.5f, 0.12f, 0.14f, 0.2f );
	gfx_begin();
	for ( i = 0; i < 16; i++ )
	{
		float t = (float)i / 15.f;
		box( &bars[i * 12], 12.5f + 25.f * (float)i, 175.f, 12.5f, 45.f, t, 0.5f, 1.f - t, 0 );
		box( &bars[( 16 + i ) * 12], 12.5f + 25.f * (float)i, 65.f, 12.5f, 45.f, t, t, t, 0 );
	}
	gfx_sprites( bars, 32 );

	check( gfx_clip( 0, 0, 100, H ) == 1 );
	check( gfx_effect( GFX_FX_BRIGHT_CONTRAST, bc_a, 2 ) == 1 );
	check( gfx_clip( 100, 0, 100, H ) == 1 );
	check( gfx_effect( GFX_FX_TINT, tint_b, 5 ) == 1 );
	check( gfx_clip( 200, 0, 100, H ) == 1 );
	check( gfx_effect( GFX_FX_BRIGHT_CONTRAST, bc_c, 2 ) == 1 );
	check( gfx_effect( GFX_FX_TINT, tint_c, 5 ) == 1 );
	check( gfx_clip( 300, 40, 50, 100 ) == 1 );
	check( gfx_effect( GFX_FX_BRIGHT_CONTRAST, bc_d, 2 ) == 1 );
	check( gfx_clip( 350, 40, 50, 100 ) == 1 );
	check( gfx_effect( GFX_FX_TINT, NULL, 0 ) == 1 );
	check( gfx_clip( 0, 0, 0, 0 ) == 1 );
	check( gfx_effect( GFX_FX_BRIGHT_CONTRAST, bc_hidden, 2 ) == 1 ); // queued, but nothing is inside the clip
	check( gfx_clip_reset() == 1 );

	// what the API refuses
	check( gfx_effect( 0, NULL, 0 ) == 0 );
	check( gfx_effect( -3, NULL, 0 ) == 0 );
	check( gfx_effect( GFX_FX_ID_MAX + 1, NULL, 0 ) == 0 );
	check( gfx_effect( 255, NULL, 0 ) == 0 );

	box( disc, 200.f, 120.f, 30.f, 30.f, 1.f, 1.f, 1.f, 1 ); // drawn after the effects: untouched by them
	gfx_sprites( disc, 1 );
	return gfx_end();
}
