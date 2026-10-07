// The clip test scene: the same things drawn inside several clip rectangles, to see that sprites and meshes are cut alike on every backend, that a rectangle
// partly off the picture is cut to it, that an empty one hides everything, that a reset shows everything again and that a frame starts without a clip.
// One pixel is one world unit (y up) and the clip counts pixels from the TOP, so the rectangles below are where they look on the picture.
#include <stdio.h>

#include "../gfx2d.h"

#define W 400
#define H 240

static void sprite( float* o, float x, float y, float hw, float hh, float rot, float r, float g, float b, int shape )
{
	o[0] = x; o[1] = y; o[2] = hw; o[3] = hh; o[4] = rot;
	o[5] = r; o[6] = g; o[7] = b; o[8] = 1.f;
	o[9] = (float)shape; o[10] = 0.f; o[11] = 0.f;
}

static int tri( float* o, float x0, float y0, float x1, float y1, float r, float g, float b )
{
	// a quad of two triangles with a tint, the white texture
	float q[6][2] = { { x0, y0 }, { x1, y0 }, { x1, y1 }, { x0, y0 }, { x1, y1 }, { x0, y1 } };
	int i;
	for ( i = 0; i < 6; i++ )
	{
		o[i * 8] = q[i][0]; o[i * 8 + 1] = q[i][1]; o[i * 8 + 2] = 0.f; o[i * 8 + 3] = 0.f;
		o[i * 8 + 4] = r; o[i * 8 + 5] = g; o[i * 8 + 6] = b; o[i * 8 + 7] = 1.f;
	}
	return 6;
}

// A tile of the picture: a big rotated box and a disc (sprites) and a tinted quad and a line of text (meshes), all of them overlapping the tile's edges
static void tile( float cx, float cy )
{
	float s[12], v[6 * 8 * 2];
	float g[9];
	int n = 0, f = 0, i;
	sprite( s, cx, cy, 34.7f, 22.3f, 0.4f, 0.9f, 0.4f, 0.2f, 0 );
	gfx_sprites( s, 1 );
	sprite( s, cx + 9.3f, cy - 4.1f, 17.3f, 17.3f, 0.f, 0.3f, 0.8f, 0.9f, 1 );
	gfx_sprites( s, 1 );
	n = tri( v, cx - 29.5f, cy - 9.3f, cx + 31.3f, cy + 5.7f, 0.5f, 0.9f, 0.3f );
	gfx_triangles( v, n, 0 );
	n = 0;
	{
		float x = cx - 33.f;
		const char* t = "Clip me";
		float base = cy - 3.f;
		for ( i = 0; t[i]; i++ )
		{
			float u0, v0, u1, v1, x0, x1, y0, y1;
			float q[6][4];
			int k;
			gfx_font_glyph( f, (unsigned char)t[i], g );
			u0 = g[0]; v0 = g[1]; u1 = g[2]; v1 = g[3];
			x0 = x + g[6]; x1 = x0 + g[4]; y1 = base + g[7]; y0 = y1 - g[5];
			{
				float cq[6][4] = { { x0, y0, u0, v1 }, { x1, y0, u1, v1 }, { x1, y1, u1, v0 }, { x0, y0, u0, v1 }, { x1, y1, u1, v0 }, { x0, y1, u0, v0 } };
				for ( k = 0; k < 6; k++ )
				{
					q[k][0] = cq[k][0]; q[k][1] = cq[k][1]; q[k][2] = cq[k][2]; q[k][3] = cq[k][3];
					v[(n + k) * 8] = q[k][0]; v[(n + k) * 8 + 1] = q[k][1]; v[(n + k) * 8 + 2] = q[k][2]; v[(n + k) * 8 + 3] = q[k][3];
					v[(n + k) * 8 + 4] = 1.f; v[(n + k) * 8 + 5] = 1.f; v[(n + k) * 8 + 6] = 0.2f; v[(n + k) * 8 + 7] = 1.f;
				}
			}
			n += 6;
			x += g[8];
			if ( n + 6 > 12 )
			{
				gfx_triangles( v, n, gfx_font_texture( f ) );
				n = 0;
			}
		}
		if ( n > 0 )
			gfx_triangles( v, n, gfx_font_texture( f ) );
	}
}

int scene_init( void )
{
	return gfx_init( W, H );
}

int scene_frame( int n )
{
	(void)n;
	gfx_camera( W * 0.5f, H * 0.5f, H * 0.5f, 0.12f, 0.14f, 0.2f );
	gfx_begin();
	tile( 60.f, 180.f );                       // no clip: the frame starts without one
	gfx_clip( 120, 20, 60, 50 );               // a rectangle inside the picture: the tile at (160, 180) is cut to it
	tile( 160.f, 180.f );
	gfx_clip( 220, 20, 40, 40 );               // a second one right after
	tile( 260.f, 180.f );
	gfx_clip( 320, 0, 200, 40 );               // partly off the picture to the right: cut to it
	tile( 360.f, 220.f );
	gfx_clip( 10, 100, 0, 30 );                // empty: nothing shows
	tile( 60.f, 100.f );
	gfx_clip( -50, 90, 160, 30 );              // partly off to the left
	tile( 60.f, 100.f );
	gfx_clip( 150, 80, 90, 50 );
	tile( 190.f, 100.f );
	gfx_clip_reset();                          // everything again
	tile( 300.f, 100.f );
	gfx_clip( 20, 160, 120, 60 );              // lower left, text and sprites both
	tile( 60.f, 40.f );
	tile( 90.f, 40.f );
	gfx_clip( 0, 0, 0, 0 );                    // hidden to the end of the frame
	tile( 300.f, 40.f );
	return gfx_end();
}
