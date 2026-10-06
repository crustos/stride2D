// Native test driver: draws the test scene (scene.c) for N frames with whatever backend the build and STRIDE2D_GFX pick, prints one line per frame
// (the hash of the picture and what the frame cost), and writes the last picture as frame_NNNN.ppm in the current directory.
//
//     driver [FRAMES] [--window SECONDS]
//
// --window keeps drawing for SECONDS, paced by the window, so a person can look at it (needs a display).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../gfx2d.h"

int scene_init( void );
int scene_frame( int n );

int main( int argc, char** argv )
{
	int frames = 3, i, seconds = 0;
	for ( i = 1; i < argc; i++ )
	{
		if ( strcmp( argv[i], "--window" ) == 0 && i + 1 < argc )
			seconds = atoi( argv[++i] );
		else
			frames = atoi( argv[i] );
	}
	if ( frames < 1 )
		frames = 1;
	if ( !scene_init() )
	{
		printf( "init failed\n" );
		return 1;
	}
	printf( "backend=%d windowed=%d\n", gfx_backend(), gfx_stat( GFX_STAT_WINDOWED ) );
	for ( i = 0; i < frames; i++ )
	{
		scene_frame( i );
		printf( "frame %d hash %08x calls %d sprites %d vertices %d bytes %d\n", i, (unsigned)gfx_frame_hash(), gfx_stat( GFX_STAT_DRAW_CALLS ),
				gfx_stat( GFX_STAT_SPRITES ), gfx_stat( GFX_STAT_VERTICES ), gfx_stat( GFX_STAT_BYTES_UPLOADED ) );
	}
	gfx_save_frame( frames - 1 );
	if ( seconds > 0 )
	{
		time_t end = time( NULL ) + seconds;
		int n = frames;
		while ( time( NULL ) < end )
		{
			if ( !scene_frame( n++ ) ) // the window was closed
				break;
		}
		printf( "ran %d frames in a window\n", n - frames );
	}
	gfx_shutdown();
	return 0;
}
