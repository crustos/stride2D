// The scene_lights scene: the bars of the fx2 scene lit by one scene_lights effect, which the editor's Lights window drives. Five lights over a green-ish ambient:
// two point lights (one with a different color), a spot light pointing right, a spot pointing up-left with a wide soft cone, and one that is off (intensity 0);
// quadratic falloff, exposure 1.3 and mix 0.85. tools/gfx_test.py works out the pixels from the formulas written out again in Python.
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

// light i: x y radius intensity (8 + 12 i ..), color (+4), direction, cone, softness, kind (+8 .. +11)
static void light( float* p, int i, float x, float y, float r, float k, float cr, float cg, float cb, float a, float cone, float soft, float kind )
{
	float* q = &p[8 + 12 * i];
	q[0] = x; q[1] = y; q[2] = r; q[3] = k;
	q[4] = cr; q[5] = cg; q[6] = cb; q[7] = 1.f;
	q[8] = a; q[9] = cone; q[10] = soft; q[11] = kind;
}

int scene_frame( int n )
{
	float bars[32 * 12];
	float p[GFX_FX_PARAMS] = { 0 };
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
	p[0] = 0.1f; p[1] = 0.22f; p[2] = 0.15f; p[3] = 1.f;      // ambient
	p[4] = 2.f; p[5] = 0.1f; p[6] = 1.3f; p[7] = 0.85f;      // falloff (quadratic), glow, exposure, mix
	light( p, 0, 0.2f, 0.3f, 0.4f, 1.f, 1.f, 0.85f, 0.6f, 0.f, 30.f, 0.4f, 0.f );
	light( p, 1, 0.45f, 0.75f, 0.35f, 1.5f, 0.4f, 0.7f, 1.f, 0.f, 30.f, 0.4f, 0.f );
	light( p, 2, 0.55f, 0.3f, 0.7f, 1.2f, 1.f, 1.f, 0.9f, 0.f, 25.f, 0.5f, 1.f );          // a spot pointing right
	light( p, 3, 0.95f, 0.9f, 0.8f, 1.f, 1.f, 0.6f, 0.9f, 140.f, 40.f, 0.8f, 1.f );        // a spot up and to the left
	light( p, 4, 0.8f, 0.5f, 0.5f, 0.f, 1.f, 1.f, 1.f, 0.f, 30.f, 0.4f, 0.f );             // off
	if ( gfx_effect( GFX_FX_SCENE_LIGHTS, p, GFX_FX_PARAMS ) != 1 )
		g_api_fail++;
	return gfx_end();
}
