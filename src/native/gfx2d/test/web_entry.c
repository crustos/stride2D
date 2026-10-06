// The test scene as a WebAssembly reactor for a page: the two functions stride2d_web.js calls. A translated game gets the same two (tools/wasm_build.py adds them
// around the game's static Init() and Frame()); this is the hand-written equivalent for the renderer's own tests.
#include <stdio.h>

#include "../gfx2d.h"

int scene_init( void );
int scene_frame( int n );

static int g_frame;

// Prints what the page delivered (gfx_poll_event), so a test can read it from the page's log.
static void drain( void )
{
	int e[5];
	while ( gfx_poll_event( e ) )
		printf( "ev %d %d %d %d %d\n", e[0], e[1], e[2], e[3], e[4] );
	fflush( stdout );
}

__attribute__( ( export_name( "stride2d_init" ) ) ) int stride2d_init( void )
{
	if ( !scene_init() )
	{
		printf( "scene_init failed\n" );
		return 1;
	}
	g_frame = 0;
	return 0;
}

__attribute__( ( export_name( "stride2d_frame" ) ) ) void stride2d_frame( void )
{
	scene_frame( g_frame++ );
	drain();
}
