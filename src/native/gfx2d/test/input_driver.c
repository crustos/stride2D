// Prints the input a real window (or a page's stand-in) delivers, one line per event: "ev TYPE A B C D". Draws a plain frame each loop so the window has
// something to show. Stops on a close event or after SECONDS (default 5), and on a key with the code GFX_KEY_ESCAPE.
//
//     input_driver [SECONDS]
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "../gfx2d.h"

int main( int argc, char** argv )
{
	int seconds = argc > 1 ? atoi( argv[1] ) : 5, e[5], done = 0;
	time_t end;
	if ( !gfx_init( 320, 200 ) )
	{
		printf( "init failed\n" );
		return 1;
	}
	printf( "backend=%d windowed=%d\n", gfx_backend(), gfx_stat( GFX_STAT_WINDOWED ) );
	fflush( stdout );
	end = time( NULL ) + seconds;
	while ( !done && time( NULL ) < end )
	{
		gfx_camera( 0.f, 0.f, 5.f, 0.1f, 0.1f, 0.2f );
		gfx_begin();
		if ( !gfx_end() )
			done = 1;
		while ( gfx_poll_event( e ) )
		{
			printf( "ev %d %d %d %d %d\n", e[0], e[1], e[2], e[3], e[4] );
			fflush( stdout );
			if ( e[0] == GFX_EVENT_CLOSE || ( e[0] == GFX_EVENT_KEY_DOWN && e[1] == GFX_KEY_ESCAPE ) )
				done = 1;
		}
		{
			struct timespec ts = { 0, 5000000 };
			nanosleep( &ts, NULL );
		}
	}
	gfx_shutdown();
	return 0;
}
