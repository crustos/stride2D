// The test scene, drawn through the public API (gfx2d.h) and nothing else. The same file is built into a native test program (driver.c) and into a
// WebAssembly module (web_entry.c) so the same calls are drawn by every backend and the pictures can be compared.
//
// It is made to show each thing a backend can get wrong: layers given in the opposite order to their depth, translucency, a rotated box, a disc and a
// rotated ellipse (their edges), vertex colours, a texture whose FIRST row is a different colour from its last (a flipped image shows at once), nearest
// and linear filtering, a texture changed after it was made (the terrain case), and draws interleaved in call order. Coordinates are deliberately not
// round numbers, so no edge falls exactly on a pixel centre, where two correct rasterisers may disagree.
#include <math.h>
#include <string.h>

#include "../gfx2d.h"

#define W 400
#define H 240

static int g_flag, g_linear, g_terrain;
static uint8_t g_terrain_px[16 * 16 * 4];

static void sprite( float* o, float x, float y, float hw, float hh, float rot, float r, float g, float b, float a, int shape, int layer )
{
	o[0] = x; o[1] = y; o[2] = hw; o[3] = hh; o[4] = rot;
	o[5] = r; o[6] = g; o[7] = b; o[8] = a;
	o[9] = (float)shape; o[10] = (float)layer; o[11] = 0.f;
}

static void vertex( float* o, float x, float y, float u, float v, float r, float g, float b, float a )
{
	o[0] = x; o[1] = y; o[2] = u; o[3] = v; o[4] = r; o[5] = g; o[6] = b; o[7] = a;
}

// two triangles for the quad with corners (x0, y0) bottom left to (x1, y1) top right; v = vt at the top edge, vb at the bottom
static int quad( float* o, float x0, float y0, float x1, float y1, float vt, float vb, float r, float g, float b, float a )
{
	vertex( o + 0, x0, y0, 0.f, vb, r, g, b, a );
	vertex( o + 8, x1, y0, 1.f, vb, r, g, b, a );
	vertex( o + 16, x1, y1, 1.f, vt, r, g, b, a );
	vertex( o + 24, x0, y0, 0.f, vb, r, g, b, a );
	vertex( o + 32, x1, y1, 1.f, vt, r, g, b, a );
	vertex( o + 40, x0, y1, 0.f, vt, r, g, b, a );
	return 6;
}

int scene_width( void ) { return W; }
int scene_height( void ) { return H; }

int scene_init( void )
{
	uint8_t flag[8 * 8 * 4], check[4 * 4 * 4];
	int x, y;
	if ( !gfx_init( W, H ) )
		return 0;
	// an 8 x 8 image: red grows to the right, green DOWN the rows (row 0 has none), a white pixel in the first row's first column
	for ( y = 0; y < 8; y++ )
		for ( x = 0; x < 8; x++ )
		{
			uint8_t* p = &flag[( y * 8 + x ) * 4];
			p[0] = (uint8_t)( x * 36 );
			p[1] = (uint8_t)( y * 36 );
			p[2] = 90;
			p[3] = 255;
		}
	flag[0] = flag[1] = flag[2] = 255;
	// a 4 x 4 black and white check, magnified with linear filtering
	for ( y = 0; y < 4; y++ )
		for ( x = 0; x < 4; x++ )
		{
			uint8_t v = ( ( x + y ) & 1 ) ? 255 : 30;
			uint8_t* p = &check[( y * 4 + x ) * 4];
			p[0] = v; p[1] = v; p[2] = v; p[3] = 255;
		}
	g_flag = gfx_texture( 8, 8, GFX_FILTER_NEAREST, flag );
	g_linear = gfx_texture( 4, 4, GFX_FILTER_LINEAR, check );
	memset( g_terrain_px, 0, sizeof g_terrain_px ); // fully transparent, filled in by scene_frame
	g_terrain = gfx_texture( 16, 16, GFX_FILTER_NEAREST, g_terrain_px );
	return g_flag > 0 && g_linear > 0 && g_terrain > 0;
}

// Draws frame n. Returns what gfx_end returns: 1 while the window (if there is one) is open.
int scene_frame( int n )
{
	float a = (float)n * 0.05f;
	float s[GFX_SPRITE_FLOATS * 16];
	float v[GFX_MESH_VERTEX_FLOATS * 6 * 4];
	int ns = 0;

	if ( n >= 1 ) // dig into the terrain texture: only the rectangle that changed is sent
	{
		int x0 = ( n * 3 ) % 12, y0 = 2 + ( n % 5 ), x, y;
		for ( y = y0; y < y0 + 3; y++ )
			for ( x = x0; x < x0 + 4; x++ )
			{
				uint8_t* p = &g_terrain_px[( y * 16 + x ) * 4];
				p[0] = 150; p[1] = (uint8_t)( 80 + x * 6 ); p[2] = 40; p[3] = 255;
			}
		gfx_texture_update( g_terrain, x0, y0, 4, 3, g_terrain_px );
	}

	gfx_camera( 0.17f, 0.11f, 6.f, 0.10f, 0.12f, 0.17f );
	gfx_begin();

	// sprites. The purple box (layer 8) is GIVEN before the orange one (layer 2) and must still end up on top of it.
	sprite( s + GFX_SPRITE_FLOATS * ns++, 0.13f, -4.37f, 7.9f, 0.83f, 0.f, 0.35f, 0.38f, 0.42f, 1.f, GFX_SHAPE_BOX, 1 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, -3.17f, 1.21f, 1.1f, 0.55f, 0.4f + a, 0.9f, 0.25f, 0.2f, 1.f, GFX_SHAPE_BOX, 5 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, -2.6f, 1.5f, 1.0f, 1.0f, -0.3f, 0.2f, 0.4f, 0.95f, 0.55f, GFX_SHAPE_BOX, 6 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, 2.43f, 2.07f, 1.37f, 1.37f, 0.f, 0.2f, 0.8f, 0.35f, 1.f, GFX_SHAPE_DISC, 3 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, 3.11f, -1.07f, 1.6f, 0.7f, 0.6f, 0.95f, 0.85f, 0.2f, 0.9f, GFX_SHAPE_DISC, 4 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, 0.71f, 2.03f, 0.9f, 0.9f, 0.2f, 0.6f, 0.2f, 0.8f, 1.f, GFX_SHAPE_BOX, 8 );
	sprite( s + GFX_SPRITE_FLOATS * ns++, 0.43f, 1.77f, 0.9f, 0.9f, -0.2f, 1.f, 0.55f, 0.1f, 1.f, GFX_SHAPE_BOX, 2 );
	gfx_sprites( s, ns );

	// the 8 x 8 image on a quad, its first row (red-less, with the white pixel) at the TOP; then a gradient triangle on the white texel; then the
	// magnified check; then the terrain texture
	quad( v, -5.43f, -3.31f, -3.27f, -1.07f, 0.f, 1.f, 1.f, 1.f, 1.f, 1.f );
	gfx_triangles( v, 6, g_flag );

	vertex( v + 0, -0.83f, -2.93f, 0.f, 0.f, 1.f, 0.f, 0.f, 1.f );
	vertex( v + 8, 0.97f, -2.71f, 0.f, 0.f, 0.f, 1.f, 0.f, 1.f );
	vertex( v + 16, 0.11f, -0.61f, 0.f, 0.f, 0.f, 0.f, 1.f, 0.6f );
	gfx_triangles( v, 3, 0 );

	quad( v, 1.47f, -3.57f, 3.03f, -2.01f, 0.f, 1.f, 1.f, 0.9f, 0.7f, 1.f );
	gfx_triangles( v, 6, g_linear );

	quad( v, 4.21f, -3.43f, 5.67f, -1.97f, 0.f, 1.f, 1.f, 1.f, 1.f, 1.f );
	gfx_triangles( v, 6, g_terrain );

	// drawn after the meshes, so on top of them whatever the layer
	ns = 0;
	sprite( s, 2.9f, 2.5f, 0.4f, 0.4f, 0.f, 1.f, 1.f, 1.f, 0.8f, GFX_SHAPE_DISC, 0 );
	sprite( s + GFX_SPRITE_FLOATS, -4.35f, -2.19f, 0.31f, 0.31f, 0.f, 0.1f, 0.9f, 0.9f, 0.85f, GFX_SHAPE_DISC, 0 );
	gfx_sprites( s, 2 );

	return gfx_end();
}
