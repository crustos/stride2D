// The test scene as a WebAssembly reactor for a page: the two functions stride2d_web.js calls. A translated game gets the same two (tools/wasm_build.py adds them
// around the game's static Init() and Frame()); this is the hand-written equivalent for the renderer's own tests.
#include <stdio.h>

int scene_init( void );
int scene_frame( int n );

static int g_frame;

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
}
