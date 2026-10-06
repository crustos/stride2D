// gfx2d GL backend: OpenGL ES 3 on the desktop, through EGL, with an X11 window when there is a display and offscreen (EGL surfaceless) when there is not.
//
// EVERYTHING IS LOADED AT RUN TIME. libEGL, libGLESv2 and libX11 are opened with dlopen and their functions looked up by name, against the small set of
// declarations just below, so this file builds with nothing but a C compiler (no EGL, GLES or X11 development packages), and a player built here still
// starts on a machine that has none of them: gfx_init then fails in this backend and the core falls back to the CPU one. (X11's own header is used,
// if the build machine has it, only for the sizes of its structures; without it the window is left out and the backend draws offscreen.)
//
// The picture is always drawn into an offscreen framebuffer of the size asked for. A window shows it with one blit and a buffer swap, and reading the
// picture back (gfx_pixel, gfx_frame_hash) reads that framebuffer, so a window and no window draw, and read back, exactly the same pixels.
#include <dlfcn.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gfx2d_internal.h"

#if defined( __has_include ) && !defined( GFX_NO_X11 ) // -DGFX_NO_X11 builds without a window even where the headers are there
#if __has_include( <X11/Xlib.h> ) && __has_include( <X11/Xutil.h> )
#define GFX_HAVE_X11_HEADERS 1
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#endif
#endif

// ---- the little of GLES 3 and EGL 1.4 this file uses ------------------------------------------------------------------------------------

typedef unsigned int GLenum, GLuint, GLbitfield;
typedef int GLint, GLsizei;
typedef unsigned char GLboolean;
typedef float GLfloat;
typedef char GLchar;
typedef ptrdiff_t GLsizeiptr, GLintptr;

#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_TRIANGLES 0x0004
#define GL_TRIANGLE_STRIP 0x0005
#define GL_BLEND 0x0BE2
#define GL_ZERO 0
#define GL_ONE 1
#define GL_SRC_ALPHA 0x0302
#define GL_ONE_MINUS_SRC_ALPHA 0x0303
#define GL_UNSIGNED_BYTE 0x1401
#define GL_UNSIGNED_INT 0x1405
#define GL_FLOAT 0x1406
#define GL_ARRAY_BUFFER 0x8892
#define GL_DYNAMIC_DRAW 0x88E8
#define GL_VERTEX_SHADER 0x8B31
#define GL_FRAGMENT_SHADER 0x8B30
#define GL_COMPILE_STATUS 0x8B81
#define GL_LINK_STATUS 0x8B82
#define GL_INFO_LOG_LENGTH 0x8B84
#define GL_TEXTURE_2D 0x0DE1
#define GL_TEXTURE0 0x84C0
#define GL_TEXTURE_MAG_FILTER 0x2800
#define GL_TEXTURE_MIN_FILTER 0x2801
#define GL_TEXTURE_WRAP_S 0x2802
#define GL_TEXTURE_WRAP_T 0x2803
#define GL_NEAREST 0x2600
#define GL_LINEAR 0x2601
#define GL_CLAMP_TO_EDGE 0x812F
#define GL_RGBA 0x1908
#define GL_RGBA8 0x8058
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#define GL_UNPACK_SKIP_ROWS 0x0CF3
#define GL_UNPACK_SKIP_PIXELS 0x0CF4
#define GL_UNPACK_ALIGNMENT 0x0CF5
#define GL_PACK_ALIGNMENT 0x0D05
#define GL_FRAMEBUFFER 0x8D40
#define GL_READ_FRAMEBUFFER 0x8CA8
#define GL_DRAW_FRAMEBUFFER 0x8CA9
#define GL_RENDERBUFFER 0x8D41
#define GL_COLOR_ATTACHMENT0 0x8CE0
#define GL_FRAMEBUFFER_COMPLETE 0x8CD5
#define GL_VERSION 0x1F02

#define GL_FUNCS( X )                                                                                                                                         \
	X( void, glClearColor, ( GLfloat, GLfloat, GLfloat, GLfloat ) )                                                                                           \
	X( void, glClear, ( GLbitfield ) )                                                                                                                        \
	X( void, glViewport, ( GLint, GLint, GLsizei, GLsizei ) )                                                                                                 \
	X( void, glEnable, ( GLenum ) )                                                                                                                           \
	X( void, glBlendFuncSeparate, ( GLenum, GLenum, GLenum, GLenum ) )                                                                                        \
	X( GLuint, glCreateShader, ( GLenum ) )                                                                                                                   \
	X( void, glShaderSource, ( GLuint, GLsizei, const GLchar* const*, const GLint* ) )                                                                        \
	X( void, glCompileShader, ( GLuint ) )                                                                                                                    \
	X( void, glGetShaderiv, ( GLuint, GLenum, GLint* ) )                                                                                                      \
	X( void, glGetShaderInfoLog, ( GLuint, GLsizei, GLsizei*, GLchar* ) )                                                                                     \
	X( void, glDeleteShader, ( GLuint ) )                                                                                                                     \
	X( GLuint, glCreateProgram, ( void ) )                                                                                                                    \
	X( void, glAttachShader, ( GLuint, GLuint ) )                                                                                                             \
	X( void, glLinkProgram, ( GLuint ) )                                                                                                                      \
	X( void, glGetProgramiv, ( GLuint, GLenum, GLint* ) )                                                                                                     \
	X( void, glGetProgramInfoLog, ( GLuint, GLsizei, GLsizei*, GLchar* ) )                                                                                    \
	X( void, glUseProgram, ( GLuint ) )                                                                                                                       \
	X( void, glDeleteProgram, ( GLuint ) )                                                                                                                    \
	X( GLint, glGetUniformLocation, ( GLuint, const GLchar* ) )                                                                                               \
	X( void, glUniform4f, ( GLint, GLfloat, GLfloat, GLfloat, GLfloat ) )                                                                                     \
	X( void, glUniform1i, ( GLint, GLint ) )                                                                                                                  \
	X( void, glGenBuffers, ( GLsizei, GLuint* ) )                                                                                                             \
	X( void, glDeleteBuffers, ( GLsizei, const GLuint* ) )                                                                                                    \
	X( void, glBindBuffer, ( GLenum, GLuint ) )                                                                                                               \
	X( void, glBufferData, ( GLenum, GLsizeiptr, const void*, GLenum ) )                                                                                      \
	X( void, glBufferSubData, ( GLenum, GLintptr, GLsizeiptr, const void* ) )                                                                                 \
	X( void, glGenVertexArrays, ( GLsizei, GLuint* ) )                                                                                                        \
	X( void, glDeleteVertexArrays, ( GLsizei, const GLuint* ) )                                                                                               \
	X( void, glBindVertexArray, ( GLuint ) )                                                                                                                  \
	X( void, glEnableVertexAttribArray, ( GLuint ) )                                                                                                          \
	X( void, glVertexAttribPointer, ( GLuint, GLint, GLenum, GLboolean, GLsizei, const void* ) )                                                              \
	X( void, glVertexAttribIPointer, ( GLuint, GLint, GLenum, GLsizei, const void* ) )                                                                        \
	X( void, glVertexAttribDivisor, ( GLuint, GLuint ) )                                                                                                      \
	X( void, glDrawArrays, ( GLenum, GLint, GLsizei ) )                                                                                                       \
	X( void, glDrawArraysInstanced, ( GLenum, GLint, GLsizei, GLsizei ) )                                                                                     \
	X( void, glGenTextures, ( GLsizei, GLuint* ) )                                                                                                            \
	X( void, glDeleteTextures, ( GLsizei, const GLuint* ) )                                                                                                   \
	X( void, glBindTexture, ( GLenum, GLuint ) )                                                                                                              \
	X( void, glActiveTexture, ( GLenum ) )                                                                                                                    \
	X( void, glTexImage2D, ( GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void* ) )                                                   \
	X( void, glTexSubImage2D, ( GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void* ) )                                                \
	X( void, glTexParameteri, ( GLenum, GLenum, GLint ) )                                                                                                     \
	X( void, glPixelStorei, ( GLenum, GLint ) )                                                                                                               \
	X( void, glGenFramebuffers, ( GLsizei, GLuint* ) )                                                                                                        \
	X( void, glDeleteFramebuffers, ( GLsizei, const GLuint* ) )                                                                                               \
	X( void, glBindFramebuffer, ( GLenum, GLuint ) )                                                                                                          \
	X( void, glGenRenderbuffers, ( GLsizei, GLuint* ) )                                                                                                       \
	X( void, glDeleteRenderbuffers, ( GLsizei, const GLuint* ) )                                                                                              \
	X( void, glBindRenderbuffer, ( GLenum, GLuint ) )                                                                                                         \
	X( void, glRenderbufferStorage, ( GLenum, GLenum, GLsizei, GLsizei ) )                                                                                    \
	X( void, glFramebufferRenderbuffer, ( GLenum, GLenum, GLenum, GLuint ) )                                                                                  \
	X( GLenum, glCheckFramebufferStatus, ( GLenum ) )                                                                                                         \
	X( void, glBlitFramebuffer, ( GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLbitfield, GLenum ) )                                              \
	X( void, glReadPixels, ( GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void* ) )                                                                        \
	X( void, glFinish, ( void ) )                                                                                                                             \
	X( const unsigned char*, glGetString, ( GLenum ) )

#define X( ret, name, args ) static ret( *name ) args;
GL_FUNCS( X )
#undef X

typedef void* EGLDisplay;
typedef void* EGLConfig;
typedef void* EGLContext;
typedef void* EGLSurface;
typedef int EGLint;
typedef unsigned int EGLBoolean, EGLenum;

#define EGL_NONE 0x3038
#define EGL_SURFACE_TYPE 0x3033
#define EGL_PBUFFER_BIT 0x0001
#define EGL_WINDOW_BIT 0x0004
#define EGL_RENDERABLE_TYPE 0x3040
#define EGL_OPENGL_ES3_BIT 0x0040
#define EGL_RED_SIZE 0x3024
#define EGL_GREEN_SIZE 0x3023
#define EGL_BLUE_SIZE 0x3022
#define EGL_ALPHA_SIZE 0x3021
#define EGL_NATIVE_VISUAL_ID 0x302E
#define EGL_WIDTH 0x3057
#define EGL_HEIGHT 0x3056
#define EGL_CONTEXT_MAJOR_VERSION 0x3098
#define EGL_CONTEXT_MINOR_VERSION 0x30FB
#define EGL_OPENGL_ES_API 0x30A0
#define EGL_PLATFORM_SURFACELESS_MESA 0x31DD

#define EGL_FUNCS( X )                                                                                                                                        \
	X( void*, eglGetProcAddress, ( const char* ) )                                                                                                            \
	X( EGLDisplay, eglGetDisplay, ( void* ) )                                                                                                                 \
	X( EGLBoolean, eglInitialize, ( EGLDisplay, EGLint*, EGLint* ) )                                                                                          \
	X( EGLBoolean, eglTerminate, ( EGLDisplay ) )                                                                                                             \
	X( EGLBoolean, eglBindAPI, ( EGLenum ) )                                                                                                                  \
	X( EGLBoolean, eglChooseConfig, ( EGLDisplay, const EGLint*, EGLConfig*, EGLint, EGLint* ) )                                                              \
	X( EGLBoolean, eglGetConfigAttrib, ( EGLDisplay, EGLConfig, EGLint, EGLint* ) )                                                                           \
	X( EGLContext, eglCreateContext, ( EGLDisplay, EGLConfig, EGLContext, const EGLint* ) )                                                                   \
	X( EGLBoolean, eglDestroyContext, ( EGLDisplay, EGLContext ) )                                                                                            \
	X( EGLSurface, eglCreateWindowSurface, ( EGLDisplay, EGLConfig, unsigned long, const EGLint* ) )                                                          \
	X( EGLSurface, eglCreatePbufferSurface, ( EGLDisplay, EGLConfig, const EGLint* ) )                                                                        \
	X( EGLBoolean, eglDestroySurface, ( EGLDisplay, EGLSurface ) )                                                                                            \
	X( EGLBoolean, eglMakeCurrent, ( EGLDisplay, EGLSurface, EGLSurface, EGLContext ) )                                                                       \
	X( EGLBoolean, eglSwapBuffers, ( EGLDisplay, EGLSurface ) )                                                                                               \
	X( EGLBoolean, eglSwapInterval, ( EGLDisplay, EGLint ) )

#define X( ret, name, args ) static ret( *name ) args;
EGL_FUNCS( X )
#undef X

// the two ways to ask for a display on a platform; either may be missing
typedef EGLDisplay ( *PFN_getPlatformDisplay )( EGLenum, void*, const EGLint* );

// ---- state --------------------------------------------------------------------------------------------------------------------------

#define NO_SURFACE ( (EGLSurface)0 )
#define NO_CONTEXT ( (EGLContext)0 )

static void* g_egl_lib;
static void* g_gles_lib;
static EGLDisplay g_dpy;
static EGLContext g_ctx;
static EGLSurface g_surface; // the window's surface, or a 1 x 1 pbuffer when the driver has no surfaceless context, or none
static int g_have_window;
static int g_w, g_h;
static int g_running = 1;

static GLuint g_fbo, g_rbo;
static GLuint g_sprite_prog, g_mesh_prog;
static GLint g_sprite_view, g_mesh_view, g_mesh_tex;
static GLuint g_sprite_vao, g_mesh_vao, g_inst_buf, g_vert_buf;

typedef struct GlTex
{
	GLuint name;
	int w, h;
} GlTex;
static GlTex g_tex[GFX_MAX_TEXTURES];

static void why( const char* what )
{
	if ( getenv( "STRIDE2D_GFX_DEBUG" ) )
		fprintf( stderr, "gfx2d gl: %s\n", what );
}

// ---- the shaders --------------------------------------------------------------------------------------------------------------------
// The same text is in web/stride2d_web.js (WebGL2); a disc's edge is computed here, not sampled from an image, so it is sharp at any size.

static const char* const SPRITE_VERT =
	"#version 300 es\n"
	"precision highp float;\n"
	"precision highp int;\n"
	"layout(location = 0) in vec2 a_pos;\n"
	"layout(location = 1) in vec2 a_half;\n"
	"layout(location = 2) in float a_rot;\n"
	"layout(location = 3) in vec4 a_color;\n"
	"layout(location = 4) in uint a_shape;\n"
	"uniform vec4 u_view;\n"
	"out vec4 v_color;\n"
	"out vec2 v_p;\n"
	"flat out uint v_shape;\n"
	"void main() {\n"
	"  vec2 q = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;\n"
	"  vec2 l = q * a_half;\n"
	"  float cs = cos(a_rot), sn = sin(a_rot);\n"
	"  vec2 w = a_pos + vec2(cs * l.x - sn * l.y, sn * l.x + cs * l.y);\n"
	"  gl_Position = vec4(2.0 * (w - u_view.xy) / (u_view.zw - u_view.xy) - 1.0, 0.0, 1.0);\n"
	"  v_color = a_color;\n"
	"  v_p = q;\n"
	"  v_shape = a_shape;\n"
	"}\n";

static const char* const SPRITE_FRAG =
	"#version 300 es\n"
	"precision highp float;\n"
	"in vec4 v_color;\n"
	"in vec2 v_p;\n"
	"flat in uint v_shape;\n"
	"layout(location = 0) out vec4 frag;\n"
	"void main() {\n"
	"  float d = length(v_p);\n"
	"  float w = max(fwidth(d), 0.00001);\n"
	"  float cover = clamp((1.0 - d) / w + 0.5, 0.0, 1.0);\n"
	"  if (v_shape == 0u) cover = 1.0;\n"
	"  frag = vec4(v_color.rgb, v_color.a * cover);\n"
	"}\n";

static const char* const MESH_VERT =
	"#version 300 es\n"
	"precision highp float;\n"
	"layout(location = 0) in vec2 a_pos;\n"
	"layout(location = 1) in vec2 a_uv;\n"
	"layout(location = 2) in vec4 a_color;\n"
	"uniform vec4 u_view;\n"
	"out vec2 v_uv;\n"
	"out vec4 v_color;\n"
	"void main() {\n"
	"  gl_Position = vec4(2.0 * (a_pos - u_view.xy) / (u_view.zw - u_view.xy) - 1.0, 0.0, 1.0);\n"
	"  v_uv = a_uv;\n"
	"  v_color = a_color;\n"
	"}\n";

static const char* const MESH_FRAG =
	"#version 300 es\n"
	"precision highp float;\n"
	"uniform sampler2D u_tex;\n"
	"in vec2 v_uv;\n"
	"in vec4 v_color;\n"
	"layout(location = 0) out vec4 frag;\n"
	"void main() {\n"
	"  frag = texture(u_tex, v_uv) * v_color;\n"
	"}\n";

// ---- loading ------------------------------------------------------------------------------------------------------------------------

static void* load_gl( const char* name )
{
	void* p = dlsym( g_gles_lib, name );
	if ( p == NULL && eglGetProcAddress != NULL )
		p = eglGetProcAddress( name );
	return p;
}

static int load_libraries( void )
{
	const char* missing = NULL;
	g_egl_lib = dlopen( "libEGL.so.1", RTLD_NOW | RTLD_LOCAL );
	if ( g_egl_lib == NULL )
		g_egl_lib = dlopen( "libEGL.so", RTLD_NOW | RTLD_LOCAL );
	g_gles_lib = dlopen( "libGLESv2.so.2", RTLD_NOW | RTLD_LOCAL );
	if ( g_gles_lib == NULL )
		g_gles_lib = dlopen( "libGLESv2.so", RTLD_NOW | RTLD_LOCAL );
	if ( g_egl_lib == NULL || g_gles_lib == NULL )
	{
		why( "libEGL or libGLESv2 is not installed" );
		return 0;
	}
#define X( ret, name, args )                                                                                                                                  \
	name = (ret( * ) args)dlsym( g_egl_lib, #name );                                                                                                          \
	if ( name == NULL )                                                                                                                                       \
		missing = #name;
	EGL_FUNCS( X )
#undef X
	if ( missing != NULL )
	{
		why( missing );
		return 0;
	}
#define X( ret, name, args )                                                                                                                                  \
	name = (ret( * ) args)load_gl( #name );                                                                                                                   \
	if ( name == NULL )                                                                                                                                       \
		missing = #name;
	GL_FUNCS( X )
#undef X
	if ( missing != NULL )
	{
		why( missing );
		return 0;
	}
	return 1;
}

static GLuint compile( GLenum type, const char* src )
{
	GLuint s = glCreateShader( type );
	GLint ok = 0;
	glShaderSource( s, 1, &src, NULL );
	glCompileShader( s );
	glGetShaderiv( s, GL_COMPILE_STATUS, &ok );
	if ( !ok )
	{
		char log[512];
		GLsizei n = 0;
		glGetShaderInfoLog( s, sizeof log - 1, &n, log );
		log[n] = 0;
		why( log );
		glDeleteShader( s );
		return 0;
	}
	return s;
}

static GLuint link_program( const char* vs, const char* fs )
{
	GLuint v = compile( GL_VERTEX_SHADER, vs ), f = compile( GL_FRAGMENT_SHADER, fs ), p;
	GLint ok = 0;
	if ( !v || !f )
		return 0;
	p = glCreateProgram();
	glAttachShader( p, v );
	glAttachShader( p, f );
	glLinkProgram( p );
	glDeleteShader( v );
	glDeleteShader( f );
	glGetProgramiv( p, GL_LINK_STATUS, &ok );
	if ( !ok )
	{
		char log[512];
		GLsizei n = 0;
		glGetProgramInfoLog( p, sizeof log - 1, &n, log );
		log[n] = 0;
		why( log );
		glDeleteProgram( p );
		return 0;
	}
	return p;
}

// ---- the window (X11) ---------------------------------------------------------------------------------------------------------------

#ifdef GFX_HAVE_X11_HEADERS

static struct
{
	void* lib;
	__typeof__( XOpenDisplay )* f_OpenDisplay;
	__typeof__( XCloseDisplay )* f_CloseDisplay;
	__typeof__( XDefaultScreen )* f_DefaultScreen;
	__typeof__( XRootWindow )* f_RootWindow;
	__typeof__( XDefaultDepth )* f_DefaultDepth;
	__typeof__( XDefaultVisual )* f_DefaultVisual;
	__typeof__( XCreateColormap )* f_CreateColormap;
	__typeof__( XFreeColormap )* f_FreeColormap;
	__typeof__( XCreateWindow )* f_CreateWindow;
	__typeof__( XDestroyWindow )* f_DestroyWindow;
	__typeof__( XMapWindow )* f_MapWindow;
	__typeof__( XStoreName )* f_StoreName;
	__typeof__( XInternAtom )* f_InternAtom;
	__typeof__( XSetWMProtocols )* f_SetWMProtocols;
	__typeof__( XPending )* f_Pending;
	__typeof__( XNextEvent )* f_NextEvent;
	__typeof__( XFlush )* f_Flush;
	__typeof__( XSync )* f_Sync;
	__typeof__( XGetVisualInfo )* f_GetVisualInfo;
	__typeof__( XFree )* f_Free;
	__typeof__( XAllocSizeHints )* f_AllocSizeHints;
	__typeof__( XSetWMNormalHints )* f_SetWMNormalHints;
	__typeof__( XSetErrorHandler )* f_SetErrorHandler;
} xl;

static Display* g_xdpy;
static Window g_xwin;
static Colormap g_xcmap;
static Atom g_wm_delete;
static int g_x_error;

static int x_error_handler( Display* d, XErrorEvent* e )
{
	( void )d;
	( void )e;
	g_x_error = 1; // Xlib's own handler ends the process; a window that cannot be made should only mean "draw offscreen"
	return 0;
}

static int x_load( void )
{
	const char* missing = NULL;
	xl.lib = dlopen( "libX11.so.6", RTLD_NOW | RTLD_LOCAL );
	if ( xl.lib == NULL )
		return 0;
#define XF( field, name )                                                                                                                                     \
	xl.f_##field = (__typeof__( xl.f_##field ))dlsym( xl.lib, #name );                                                                                      \
	if ( xl.f_##field == NULL )                                                                                                                              \
		missing = #name;
	XF( OpenDisplay, XOpenDisplay ) XF( CloseDisplay, XCloseDisplay ) XF( DefaultScreen, XDefaultScreen ) XF( RootWindow, XRootWindow )
	XF( DefaultDepth, XDefaultDepth ) XF( DefaultVisual, XDefaultVisual ) XF( CreateColormap, XCreateColormap ) XF( FreeColormap, XFreeColormap )
	XF( CreateWindow, XCreateWindow ) XF( DestroyWindow, XDestroyWindow ) XF( MapWindow, XMapWindow ) XF( StoreName, XStoreName )
	XF( InternAtom, XInternAtom ) XF( SetWMProtocols, XSetWMProtocols ) XF( Pending, XPending ) XF( NextEvent, XNextEvent ) XF( Flush, XFlush )
	XF( Sync, XSync ) XF( GetVisualInfo, XGetVisualInfo ) XF( Free, XFree ) XF( AllocSizeHints, XAllocSizeHints )
	XF( SetWMNormalHints, XSetWMNormalHints ) XF( SetErrorHandler, XSetErrorHandler )
#undef XF
	if ( missing != NULL )
	{
		why( missing );
		return 0;
	}
	return 1;
}

static void x_close( void )
{
	if ( g_xdpy != NULL )
	{
		if ( g_xwin )
			xl.f_DestroyWindow( g_xdpy, g_xwin );
		if ( g_xcmap )
			xl.f_FreeColormap( g_xdpy, g_xcmap );
		xl.f_Sync( g_xdpy, False );
		xl.f_CloseDisplay( g_xdpy );
	}
	g_xdpy = NULL;
	g_xwin = 0;
	g_xcmap = 0;
}

// Opens the display and a fixed-size window with the visual the EGL config wants. Returns the window, or 0 (nothing left open).
static unsigned long x_window( int width, int height, EGLDisplay* dpy_out, EGLConfig* cfg_out )
{
	static const EGLint cfg_attribs[] = { EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_RED_SIZE, 8,
										  EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE };
	EGLint major, minor, n = 0, visual_id = 0;
	EGLConfig cfg;
	XSetWindowAttributes attrs;
	XVisualInfo tmpl, *vi = NULL;
	Visual* visual;
	int depth, nvi = 0, screen;
	XSizeHints* hints;

	if ( getenv( "DISPLAY" ) == NULL || getenv( "STRIDE2D_HEADLESS" ) != NULL || !x_load() )
		return 0;
	xl.f_SetErrorHandler( x_error_handler );
	g_x_error = 0;
	g_xdpy = xl.f_OpenDisplay( NULL );
	if ( g_xdpy == NULL )
	{
		why( "cannot open the X display" );
		return 0;
	}
	*dpy_out = eglGetDisplay( (void*)g_xdpy );
	if ( *dpy_out == NULL || !eglInitialize( *dpy_out, &major, &minor ) || !eglBindAPI( EGL_OPENGL_ES_API ) ||
		 !eglChooseConfig( *dpy_out, cfg_attribs, &cfg, 1, &n ) || n < 1 )
	{
		why( "EGL has no window configuration on this display" );
		x_close();
		return 0;
	}
	*cfg_out = cfg;
	screen = xl.f_DefaultScreen( g_xdpy );
	visual = xl.f_DefaultVisual( g_xdpy, screen );
	depth = xl.f_DefaultDepth( g_xdpy, screen );
	if ( eglGetConfigAttrib( *dpy_out, cfg, EGL_NATIVE_VISUAL_ID, &visual_id ) && visual_id != 0 )
	{
		memset( &tmpl, 0, sizeof tmpl );
		tmpl.visualid = (VisualID)visual_id;
		vi = xl.f_GetVisualInfo( g_xdpy, VisualIDMask, &tmpl, &nvi );
		if ( vi != NULL && nvi > 0 )
		{
			visual = vi[0].visual;
			depth = vi[0].depth;
		}
	}
	g_xcmap = xl.f_CreateColormap( g_xdpy, xl.f_RootWindow( g_xdpy, screen ), visual, AllocNone );
	memset( &attrs, 0, sizeof attrs );
	attrs.colormap = g_xcmap;
	attrs.border_pixel = 0;
	attrs.event_mask = StructureNotifyMask;
	g_xwin = xl.f_CreateWindow( g_xdpy, xl.f_RootWindow( g_xdpy, screen ), 0, 0, (unsigned)width, (unsigned)height, 0, depth, InputOutput, visual,
							 CWColormap | CWBorderPixel | CWEventMask, &attrs );
	if ( vi != NULL )
		xl.f_Free( vi );
	if ( !g_xwin )
	{
		x_close();
		return 0;
	}
	hints = xl.f_AllocSizeHints();
	if ( hints != NULL ) // not resizable: the picture is a fixed size
	{
		hints->flags = PMinSize | PMaxSize;
		hints->min_width = hints->max_width = width;
		hints->min_height = hints->max_height = height;
		xl.f_SetWMNormalHints( g_xdpy, g_xwin, hints );
		xl.f_Free( hints );
	}
	xl.f_StoreName( g_xdpy, g_xwin, "Stride2D" );
	g_wm_delete = xl.f_InternAtom( g_xdpy, "WM_DELETE_WINDOW", False );
	xl.f_SetWMProtocols( g_xdpy, g_xwin, &g_wm_delete, 1 );
	xl.f_MapWindow( g_xdpy, g_xwin );
	xl.f_Sync( g_xdpy, False );
	if ( g_x_error )
	{
		why( "the X server refused the window" );
		x_close();
		return 0;
	}
	return (unsigned long)g_xwin;
}

static void x_pump( void )
{
	while ( g_xdpy != NULL && xl.f_Pending( g_xdpy ) > 0 )
	{
		XEvent ev;
		xl.f_NextEvent( g_xdpy, &ev );
		if ( ev.type == ClientMessage && (Atom)ev.xclient.data.l[0] == g_wm_delete )
			g_running = 0;
		else if ( ev.type == DestroyNotify )
			g_running = 0;
	}
}

#else // no X11 headers on the build machine: no window

static unsigned long x_window( int width, int height, EGLDisplay* dpy_out, EGLConfig* cfg_out )
{
	( void )width;
	( void )height;
	( void )dpy_out;
	( void )cfg_out;
	return 0;
}
static void x_close( void ) {}
static void x_pump( void ) {}

#endif

// ---- the context --------------------------------------------------------------------------------------------------------------------

static void teardown( void )
{
	int i;
	if ( g_dpy != NULL && g_ctx != NO_CONTEXT && eglMakeCurrent( g_dpy, g_surface, g_surface, g_ctx ) )
	{
		for ( i = 0; i < GFX_MAX_TEXTURES; i++ )
			if ( g_tex[i].name )
				glDeleteTextures( 1, &g_tex[i].name );
		if ( g_sprite_vao )
			glDeleteVertexArrays( 1, &g_sprite_vao );
		if ( g_mesh_vao )
			glDeleteVertexArrays( 1, &g_mesh_vao );
		if ( g_inst_buf )
			glDeleteBuffers( 1, &g_inst_buf );
		if ( g_vert_buf )
			glDeleteBuffers( 1, &g_vert_buf );
		if ( g_sprite_prog )
			glDeleteProgram( g_sprite_prog );
		if ( g_mesh_prog )
			glDeleteProgram( g_mesh_prog );
		if ( g_fbo )
			glDeleteFramebuffers( 1, &g_fbo );
		if ( g_rbo )
			glDeleteRenderbuffers( 1, &g_rbo );
	}
	memset( g_tex, 0, sizeof g_tex );
	g_sprite_vao = g_mesh_vao = g_inst_buf = g_vert_buf = g_sprite_prog = g_mesh_prog = g_fbo = g_rbo = 0;
	if ( g_dpy != NULL )
	{
		eglMakeCurrent( g_dpy, NO_SURFACE, NO_SURFACE, NO_CONTEXT );
		if ( g_surface != NO_SURFACE )
			eglDestroySurface( g_dpy, g_surface );
		if ( g_ctx != NO_CONTEXT )
			eglDestroyContext( g_dpy, g_ctx );
		eglTerminate( g_dpy );
	}
	g_dpy = NULL;
	g_ctx = NO_CONTEXT;
	g_surface = NO_SURFACE;
	x_close();
	g_have_window = 0;
}

// A display with no window system: Mesa's surfaceless platform (software or a GPU's render node), else the default display.
static EGLDisplay headless_display( void )
{
	PFN_getPlatformDisplay get = NULL;
	EGLDisplay d = NULL;
	if ( eglGetProcAddress != NULL )
	{
		get = (PFN_getPlatformDisplay)eglGetProcAddress( "eglGetPlatformDisplay" );
		if ( get == NULL )
			get = (PFN_getPlatformDisplay)eglGetProcAddress( "eglGetPlatformDisplayEXT" );
	}
	if ( get != NULL )
		d = get( EGL_PLATFORM_SURFACELESS_MESA, NULL, NULL );
	if ( d == NULL )
	{
		setenv( "EGL_PLATFORM", "surfaceless", 0 );
		d = eglGetDisplay( NULL );
	}
	return d;
}

static int make_context( int width, int height )
{
	static const EGLint ctx_attribs[] = { EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 0, EGL_NONE };
	static const EGLint cfg_attribs[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_RED_SIZE, 8,
										  EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE };
	EGLConfig cfg = NULL;
	EGLint major, minor, n = 0;
	unsigned long win = x_window( width, height, &g_dpy, &cfg );

	if ( win )
	{
		g_surface = eglCreateWindowSurface( g_dpy, cfg, win, NULL );
		g_ctx = g_surface != NO_SURFACE ? eglCreateContext( g_dpy, cfg, NO_CONTEXT, ctx_attribs ) : NO_CONTEXT;
		if ( g_ctx != NO_CONTEXT && eglMakeCurrent( g_dpy, g_surface, g_surface, g_ctx ) )
		{
			g_have_window = 1;
			eglSwapInterval( g_dpy, 1 );
			return 1;
		}
		why( "the window's context could not be made: drawing offscreen" );
		teardown();
	}

	g_dpy = headless_display();
	if ( g_dpy == NULL || !eglInitialize( g_dpy, &major, &minor ) )
	{
		why( "no EGL display" );
		g_dpy = NULL;
		return 0;
	}
	if ( !eglBindAPI( EGL_OPENGL_ES_API ) || !eglChooseConfig( g_dpy, cfg_attribs, &cfg, 1, &n ) || n < 1 )
	{
		why( "no EGL configuration for OpenGL ES 3" );
		teardown();
		return 0;
	}
	g_ctx = eglCreateContext( g_dpy, cfg, NO_CONTEXT, ctx_attribs );
	if ( g_ctx == NO_CONTEXT )
	{
		why( "no OpenGL ES 3 context" );
		teardown();
		return 0;
	}
	if ( !eglMakeCurrent( g_dpy, NO_SURFACE, NO_SURFACE, g_ctx ) ) // a driver without surfaceless contexts wants a surface, any surface
	{
		static const EGLint pb[] = { EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE };
		g_surface = eglCreatePbufferSurface( g_dpy, cfg, pb );
		if ( g_surface == NO_SURFACE || !eglMakeCurrent( g_dpy, g_surface, g_surface, g_ctx ) )
		{
			why( "the context cannot be made current" );
			teardown();
			return 0;
		}
	}
	return 1;
}

// ---- the backend --------------------------------------------------------------------------------------------------------------------

static void set_instance_pointers( int first )
{
	size_t base = (size_t)first * (size_t)GFX_INSTANCE_BYTES;
	glBindBuffer( GL_ARRAY_BUFFER, g_inst_buf );
	glVertexAttribPointer( 0, 2, GL_FLOAT, 0, GFX_INSTANCE_BYTES, (const void*)( base + offsetof( GfxInstance, x ) ) );
	glVertexAttribPointer( 1, 2, GL_FLOAT, 0, GFX_INSTANCE_BYTES, (const void*)( base + offsetof( GfxInstance, hw ) ) );
	glVertexAttribPointer( 2, 1, GL_FLOAT, 0, GFX_INSTANCE_BYTES, (const void*)( base + offsetof( GfxInstance, rot ) ) );
	glVertexAttribPointer( 3, 4, GL_UNSIGNED_BYTE, 1, GFX_INSTANCE_BYTES, (const void*)( base + offsetof( GfxInstance, rgba ) ) );
	glVertexAttribIPointer( 4, 1, GL_UNSIGNED_INT, GFX_INSTANCE_BYTES, (const void*)( base + offsetof( GfxInstance, shape ) ) );
}

static int gl_init( int width, int height )
{
	GLint status;
	const unsigned char* version;
	int i;

	if ( g_ctx != NO_CONTEXT )
		return 0;
	if ( !load_libraries() )
		return 0;
	g_running = 1;
	if ( !make_context( width, height ) )
		return 0;
	version = glGetString( GL_VERSION );
	if ( version == NULL || strstr( (const char*)version, "OpenGL ES 3" ) == NULL )
	{
		why( "the context is not OpenGL ES 3" );
		teardown();
		return 0;
	}
	g_w = width;
	g_h = height;

	glGenFramebuffers( 1, &g_fbo );
	glBindFramebuffer( GL_FRAMEBUFFER, g_fbo );
	glGenRenderbuffers( 1, &g_rbo );
	glBindRenderbuffer( GL_RENDERBUFFER, g_rbo );
	glRenderbufferStorage( GL_RENDERBUFFER, GL_RGBA8, width, height );
	glFramebufferRenderbuffer( GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, g_rbo );
	status = (GLint)glCheckFramebufferStatus( GL_FRAMEBUFFER );
	if ( status != GL_FRAMEBUFFER_COMPLETE )
	{
		why( "the offscreen framebuffer is not complete" );
		teardown();
		return 0;
	}

	g_sprite_prog = link_program( SPRITE_VERT, SPRITE_FRAG );
	g_mesh_prog = link_program( MESH_VERT, MESH_FRAG );
	if ( !g_sprite_prog || !g_mesh_prog )
	{
		teardown();
		return 0;
	}
	g_sprite_view = glGetUniformLocation( g_sprite_prog, "u_view" );
	g_mesh_view = glGetUniformLocation( g_mesh_prog, "u_view" );
	g_mesh_tex = glGetUniformLocation( g_mesh_prog, "u_tex" );

	glGenBuffers( 1, &g_inst_buf );
	glBindBuffer( GL_ARRAY_BUFFER, g_inst_buf );
	glBufferData( GL_ARRAY_BUFFER, (GLsizeiptr)GFX_MAX_SPRITES * GFX_INSTANCE_BYTES, NULL, GL_DYNAMIC_DRAW );
	glGenBuffers( 1, &g_vert_buf );
	glBindBuffer( GL_ARRAY_BUFFER, g_vert_buf );
	glBufferData( GL_ARRAY_BUFFER, (GLsizeiptr)GFX_MAX_VERTICES * GFX_VERTEX_BYTES, NULL, GL_DYNAMIC_DRAW );

	glGenVertexArrays( 1, &g_sprite_vao );
	glBindVertexArray( g_sprite_vao );
	set_instance_pointers( 0 );
	for ( i = 0; i < 5; i++ )
	{
		glEnableVertexAttribArray( (GLuint)i );
		glVertexAttribDivisor( (GLuint)i, 1 );
	}

	glGenVertexArrays( 1, &g_mesh_vao );
	glBindVertexArray( g_mesh_vao );
	glBindBuffer( GL_ARRAY_BUFFER, g_vert_buf );
	glVertexAttribPointer( 0, 2, GL_FLOAT, 0, GFX_VERTEX_BYTES, (const void*)offsetof( GfxVertex, x ) );
	glVertexAttribPointer( 1, 2, GL_FLOAT, 0, GFX_VERTEX_BYTES, (const void*)offsetof( GfxVertex, u ) );
	glVertexAttribPointer( 2, 4, GL_FLOAT, 0, GFX_VERTEX_BYTES, (const void*)offsetof( GfxVertex, r ) );
	for ( i = 0; i < 3; i++ )
		glEnableVertexAttribArray( (GLuint)i );
	glBindVertexArray( 0 );

	glEnable( GL_BLEND ); // straight alpha into the colour; the picture's own alpha stays as the background made it (1)
	glBlendFuncSeparate( GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ONE );
	glPixelStorei( GL_UNPACK_ALIGNMENT, 1 );
	glPixelStorei( GL_PACK_ALIGNMENT, 1 );
	return 1;
}

static void gl_shutdown( void )
{
	teardown();
}

static int gl_windowed( void )
{
	return g_have_window;
}

static void gl_texture_create( int id, int width, int height, int filter, const uint8_t* rgba )
{
	GLint f = filter == GFX_FILTER_LINEAR ? GL_LINEAR : GL_NEAREST;
	glGenTextures( 1, &g_tex[id].name );
	glActiveTexture( GL_TEXTURE0 );
	glBindTexture( GL_TEXTURE_2D, g_tex[id].name );
	glTexImage2D( GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba );
	glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, f );
	glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, f );
	glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE );
	glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE );
	g_tex[id].w = width;
	g_tex[id].h = height;
}

static void gl_texture_update( int id, int x, int y, int w, int h, const uint8_t* image )
{
	if ( !g_tex[id].name )
		return;
	glActiveTexture( GL_TEXTURE0 );
	glBindTexture( GL_TEXTURE_2D, g_tex[id].name );
	glPixelStorei( GL_UNPACK_ROW_LENGTH, g_tex[id].w ); // `image` is the whole picture: read the rectangle out of it in place
	glPixelStorei( GL_UNPACK_SKIP_PIXELS, x );
	glPixelStorei( GL_UNPACK_SKIP_ROWS, y );
	glTexSubImage2D( GL_TEXTURE_2D, 0, x, y, w, h, GL_RGBA, GL_UNSIGNED_BYTE, image );
	glPixelStorei( GL_UNPACK_ROW_LENGTH, 0 );
	glPixelStorei( GL_UNPACK_SKIP_PIXELS, 0 );
	glPixelStorei( GL_UNPACK_SKIP_ROWS, 0 );
}

static void gl_texture_free( int id )
{
	if ( g_tex[id].name )
		glDeleteTextures( 1, &g_tex[id].name );
	g_tex[id].name = 0;
}

static void gl_frame( const GfxFrame* f )
{
	int c;
	glBindFramebuffer( GL_FRAMEBUFFER, g_fbo );
	glViewport( 0, 0, f->width, f->height );
	glClearColor( f->bg_r, f->bg_g, f->bg_b, 1.f );
	glClear( GL_COLOR_BUFFER_BIT );
	if ( f->ninst > 0 )
	{
		glBindBuffer( GL_ARRAY_BUFFER, g_inst_buf );
		glBufferSubData( GL_ARRAY_BUFFER, 0, (GLsizeiptr)f->ninst * GFX_INSTANCE_BYTES, f->inst );
	}
	if ( f->nverts > 0 )
	{
		glBindBuffer( GL_ARRAY_BUFFER, g_vert_buf );
		glBufferSubData( GL_ARRAY_BUFFER, 0, (GLsizeiptr)f->nverts * GFX_VERTEX_BYTES, f->verts );
	}
	for ( c = 0; c < f->ncmds; c++ )
	{
		const GfxCmd* cmd = &f->cmds[c];
		if ( cmd->kind == GFXCMD_SPRITES )
		{
			glUseProgram( g_sprite_prog );
			glUniform4f( g_sprite_view, f->left, f->bottom, f->right, f->top );
			glBindVertexArray( g_sprite_vao );
			set_instance_pointers( cmd->first ); // instanced attributes have no base offset in ES 3.0: move the pointers instead
			glDrawArraysInstanced( GL_TRIANGLE_STRIP, 0, 4, cmd->count );
		}
		else if ( cmd->kind == GFXCMD_TRIANGLES )
		{
			glUseProgram( g_mesh_prog );
			glUniform4f( g_mesh_view, f->left, f->bottom, f->right, f->top );
			glUniform1i( g_mesh_tex, 0 );
			glActiveTexture( GL_TEXTURE0 );
			glBindTexture( GL_TEXTURE_2D, g_tex[cmd->texture].name ? g_tex[cmd->texture].name : g_tex[0].name );
			glBindVertexArray( g_mesh_vao );
			glDrawArrays( GL_TRIANGLES, cmd->first, cmd->count );
		}
	}
	glBindVertexArray( 0 );
}

static int gl_present( void )
{
	if ( !g_have_window )
	{
		glFinish();
		return 1;
	}
	glBindFramebuffer( GL_READ_FRAMEBUFFER, g_fbo );
	glBindFramebuffer( GL_DRAW_FRAMEBUFFER, 0 );
	glBlitFramebuffer( 0, 0, g_w, g_h, 0, 0, g_w, g_h, GL_COLOR_BUFFER_BIT, GL_NEAREST );
	eglSwapBuffers( g_dpy, g_surface );
	glBindFramebuffer( GL_FRAMEBUFFER, g_fbo );
	x_pump();
	return g_running;
}

static void gl_read( uint8_t* rgba )
{
	glBindFramebuffer( GL_FRAMEBUFFER, g_fbo );
	glReadPixels( 0, 0, g_w, g_h, GL_RGBA, GL_UNSIGNED_BYTE, rgba );
}

const GfxBackend gfx_backend_gl = {
	"gl", GFX_BACKEND_GL, gl_init, gl_shutdown, gl_windowed, gl_texture_create, gl_texture_update, gl_texture_free, gl_frame, gl_present, gl_read,
};
