// Tests the input queue through the public API only, so the same program checks every backend: events come back in order and unchanged, an empty queue leaves
// the caller's array alone, a full queue drops the NEW event and counts it, and what the API refuses it refuses. Prints one line per check and "input ok".
#include <stdio.h>
#include <string.h>

#include "../gfx2d.h"

static int failures;

static void check( int ok, const char* what )
{
	if ( !ok )
	{
		failures++;
		printf( "FAIL %s\n", what );
	}
}

int main( void )
{
	int e[5] = { 7, 7, 7, 7, 7 }, i, n, backend;
	if ( !gfx_init( 64, 48 ) )
	{
		printf( "init failed\n" );
		return 1;
	}
	backend = gfx_backend();
	check( gfx_poll_event( e ) == 0 && e[0] == 7 && e[4] == 7, "an empty queue returns 0 and leaves the array alone" );
	check( gfx_inject_event( GFX_EVENT_MOUSE_MOVE, 10, 20, 0, 0 ) == 1, "inject a move" );
	check( gfx_inject_event( GFX_EVENT_MOUSE_DOWN, 10, 20, GFX_BUTTON_RIGHT, GFX_MOD_SHIFT | GFX_MOD_CTRL ) == 1, "inject a button" );
	check( gfx_inject_event( GFX_EVENT_WHEEL, 10, 20, -120, 240 ) == 1, "inject a wheel" );
	check( gfx_inject_event( GFX_EVENT_KEY_DOWN, GFX_KEY_ENTER, 1, 0, GFX_MOD_ALT ) == 1, "inject a key" );
	check( gfx_inject_event( GFX_EVENT_TEXT, 0x20ac, 0, 0, 0 ) == 1, "inject text beyond Latin-1" );
	check( gfx_inject_event( 0, 1, 2, 3, 4 ) == 0 && gfx_inject_event( 99, 1, 2, 3, 4 ) == 0, "an unknown type is refused" );
	gfx_begin();
	gfx_end(); // a frame between inject and poll changes nothing
	check( gfx_poll_event( e ) && e[0] == GFX_EVENT_MOUSE_MOVE && e[1] == 10 && e[2] == 20 && e[3] == 0 && e[4] == 0, "first: the move" );
	check( gfx_poll_event( e ) && e[0] == GFX_EVENT_MOUSE_DOWN && e[1] == 10 && e[2] == 20 && e[3] == GFX_BUTTON_RIGHT && e[4] == 3, "second: the button, with both mods" );
	check( gfx_poll_event( e ) && e[0] == GFX_EVENT_WHEEL && e[3] == -120 && e[4] == 240, "third: the wheel" );
	check( gfx_poll_event( e ) && e[0] == GFX_EVENT_KEY_DOWN && e[1] == GFX_KEY_ENTER && e[2] == 1 && e[4] == GFX_MOD_ALT, "fourth: the key" );
	check( gfx_poll_event( e ) && e[0] == GFX_EVENT_TEXT && e[1] == 0x20ac, "fifth: the text" );
	check( gfx_poll_event( e ) == 0, "then it is empty" );

	n = 0;
	for ( i = 0; i < GFX_MAX_EVENTS + 10; i++ )
		n += gfx_inject_event( GFX_EVENT_MOUSE_MOVE, i, 0, 0, 0 );
	check( n == GFX_MAX_EVENTS && gfx_stat( GFX_STAT_EVENTS_DROPPED ) == 10, "a full queue takes GFX_MAX_EVENTS and counts the 10 it dropped" );
	for ( i = 0; i < GFX_MAX_EVENTS; i++ )
		if ( !gfx_poll_event( e ) || e[1] != i )
			break;
	check( i == GFX_MAX_EVENTS, "the ones kept are the OLDEST, in order" );
	check( gfx_poll_event( e ) == 0, "and the dropped ones are gone" );
	check( gfx_inject_event( GFX_EVENT_CLOSE, 0, 0, 0, 0 ) == 1 && gfx_poll_event( e ) && e[0] == GFX_EVENT_CLOSE, "a close event passes through" );
	gfx_shutdown();
	check( gfx_inject_event( GFX_EVENT_MOUSE_MOVE, 1, 1, 0, 0 ) == 0 && gfx_poll_event( e ) == 0, "after shutdown there is nothing" );
	if ( failures == 0 )
		printf( "input ok (backend %d)\n", backend );
	return failures ? 1 : 0;
}
