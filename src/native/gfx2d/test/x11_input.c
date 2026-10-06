// Test helper: sends a fixed sequence of input to the window named "Stride2D" the way the server would (XSendEvent), so a test can check what gfx2d turns it into.
// The sequence: move to (40,30); left button down and up there; wheel up and down; the key A (so text "a"), with Shift (text "A"); Enter; Left arrow (no
// text); then Escape. Usage: x11_input [SECONDS_TO_WAIT_FOR_THE_WINDOW]. Exits 0 if it found the window and sent everything, 1 if not.
#include <X11/Xlib.h>
#include <X11/keysym.h>
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

static Display* g_d;
static Window g_w;
static unsigned long g_time = 1000;

static void button( int type, int b, int x, int y )
{
	XEvent ev;
	memset( &ev, 0, sizeof ev );
	ev.xbutton.type = type;
	ev.xbutton.display = g_d;
	ev.xbutton.window = g_w;
	ev.xbutton.root = DefaultRootWindow( g_d );
	ev.xbutton.time = g_time += 10;
	ev.xbutton.x = x;
	ev.xbutton.y = y;
	ev.xbutton.button = (unsigned)b;
	ev.xbutton.same_screen = True;
	XSendEvent( g_d, g_w, False, type == ButtonPress ? ButtonPressMask : ButtonReleaseMask, &ev );
}

static void key( int type, KeySym ks, unsigned state )
{
	XEvent ev;
	memset( &ev, 0, sizeof ev );
	ev.xkey.type = type;
	ev.xkey.display = g_d;
	ev.xkey.window = g_w;
	ev.xkey.root = DefaultRootWindow( g_d );
	ev.xkey.time = g_time += 10;
	ev.xkey.keycode = XKeysymToKeycode( g_d, ks );
	ev.xkey.state = state;
	ev.xkey.same_screen = True;
	XSendEvent( g_d, g_w, False, type == KeyPress ? KeyPressMask : KeyReleaseMask, &ev );
}

int main( int argc, char** argv )
{
	int wait = argc > 1 ? atoi( argv[1] ) : 5, t;
	g_d = XOpenDisplay( NULL );
	if ( !g_d )
	{
		fprintf( stderr, "x11_input: no display\n" );
		return 1;
	}
	for ( t = 0; t < wait * 10; t++ )
	{
		g_w = find( g_d, DefaultRootWindow( g_d ) );
		if ( g_w )
			break;
		usleep( 100000 );
	}
	if ( !g_w )
	{
		fprintf( stderr, "x11_input: no window named Stride2D\n" );
		XCloseDisplay( g_d );
		return 1;
	}
	usleep( 300000 ); // let the window be mapped and drawing
	{
		XEvent ev;
		memset( &ev, 0, sizeof ev );
		ev.xmotion.type = MotionNotify;
		ev.xmotion.display = g_d;
		ev.xmotion.window = g_w;
		ev.xmotion.root = DefaultRootWindow( g_d );
		ev.xmotion.x = 40;
		ev.xmotion.y = 30;
		ev.xmotion.same_screen = True;
		XSendEvent( g_d, g_w, False, PointerMotionMask, &ev );
	}
	button( ButtonPress, 1, 40, 30 );
	button( ButtonRelease, 1, 40, 30 );
	button( ButtonPress, 4, 40, 30 ); // wheel up
	button( ButtonPress, 5, 40, 30 ); // wheel down
	key( KeyPress, XK_a, 0 );
	key( KeyRelease, XK_a, 0 );
	key( KeyPress, XK_a, ShiftMask );
	key( KeyRelease, XK_a, ShiftMask );
	key( KeyPress, XK_Return, 0 );
	key( KeyRelease, XK_Return, 0 );
	key( KeyPress, XK_Left, 0 );
	key( KeyRelease, XK_Left, 0 );
	key( KeyPress, XK_Escape, 0 );
	XFlush( g_d );
	usleep( 200000 );
	XCloseDisplay( g_d );
	return 0;
}
