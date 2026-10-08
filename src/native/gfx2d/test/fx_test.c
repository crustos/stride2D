// Draws the effect scene (fx_scene.c) once, prints the picture's hash and how many of the API's answers were wrong, and writes the picture as frame_0000.ppm.
//
//     fx_test
#include <stdio.h>

#include "../gfx2d.h"

int scene_init( void );
int scene_frame( int n );
int fx_scene_api_failures( void );

int main( void )
{
	if ( !scene_init() )
	{
		printf( "init failed\n" );
		return 1;
	}
	scene_frame( 0 );
	printf( "hash %08x\n", (unsigned)gfx_frame_hash() );
	printf( "api failures %d\n", fx_scene_api_failures() );
	gfx_save_frame( 0 );
	gfx_shutdown();
	return 0;
}
