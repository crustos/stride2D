// Test helper, used with LD_PRELOAD: makes dlopen fail for the graphics libraries, so a test can check what a player does on a machine that has no EGL, no GLES
// and no X11 (it must fall back to the CPU backend, not refuse to start). Everything else is opened as usual.
//
//     cc -shared -fPIC -o nodl.so nodl.c -ldl && LD_PRELOAD=./nodl.so ./driver
#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>

void* dlopen( const char* file, int flags )
{
	static void* ( *real )( const char*, int );
	if ( !real )
		real = (void* ( * )( const char*, int ))dlsym( RTLD_NEXT, "dlopen" );
	if ( file && ( strstr( file, "libEGL" ) || strstr( file, "libGLES" ) || strstr( file, "libX11" ) ) )
		return NULL;
	return real( file, flags );
}
