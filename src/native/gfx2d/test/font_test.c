// Draws the font scene (font_scene.c) once, prints the numbers the font API gives and the picture's hash, and writes the picture as frame_0000.ppm.
//
//     font_test
#include <stdio.h>

#include "../gfx2d.h"

int scene_init( void );
int scene_frame( int n );

int main( void )
{
	if ( !scene_init() )
	{
		printf( "init failed\n" );
		return 1;
	}
	scene_frame( 0 );
	printf( "hash %08x\n", (unsigned)gfx_frame_hash() );
	gfx_save_frame( 0 );
	gfx_shutdown();
	return 0;
}
