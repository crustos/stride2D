// Test helper: closes the window named "Stride2D" the way a window manager's close button does (a WM_DELETE_WINDOW message), so a test can check that
// the game's loop stops (gfx_end returns 0). Usage: x11_close [SECONDS_TO_WAIT_FOR_THE_WINDOW]. Exits 0 if it found a window and closed it, 1 if not.
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static Window find( Display* d, Window w )
{
	Window root, parent, *kids = NULL;
	unsigned n = 0, i;
	char* name = NULL;
	if ( XFetchName( d, w, &name ) && name )
	{
		int hit = strcmp( name, "Stride2D" ) == 0;
		XFree( name );
		if ( hit )
			return w;
	}
	if ( !XQueryTree( d, w, &root, &parent, &kids, &n ) )
		return 0;
	for ( i = 0; i < n; i++ )
	{
		Window r = find( d, kids[i] );
		if ( r )
		{
			XFree( kids );
			return r;
		}
	}
	if ( kids )
		XFree( kids );
	return 0;
}

int main( int argc, char** argv )
{
	int wait = argc > 1 ? atoi( argv[1] ) : 5, t;
	Display* d = XOpenDisplay( NULL );
	if ( !d )
	{
		fprintf( stderr, "x11_close: no display\n" );
		return 1;
	}
	for ( t = 0; t < wait * 10; t++ )
	{
		Window w = find( d, DefaultRootWindow( d ) );
		if ( w )
		{
			XEvent ev;
			memset( &ev, 0, sizeof ev );
			ev.xclient.type = ClientMessage;
			ev.xclient.window = w;
			ev.xclient.message_type = XInternAtom( d, "WM_PROTOCOLS", False );
			ev.xclient.format = 32;
			ev.xclient.data.l[0] = (long)XInternAtom( d, "WM_DELETE_WINDOW", False );
			ev.xclient.data.l[1] = CurrentTime;
			XSendEvent( d, w, False, NoEventMask, &ev );
			XFlush( d );
			XCloseDisplay( d );
			return 0;
		}
		usleep( 100000 );
	}
	XCloseDisplay( d );
	fprintf( stderr, "x11_close: no window named Stride2D\n" );
	return 1;
}
