// Native benchmark of the Box2D shim: no .NET, no translator. A pyramid of boxes with circles dropped on it.
// Prints a hash of the final state of every body: an optimization must not change it.
//   python3 build.py bench            build + run;   python3 build.py bench --cachegrind
#include "box2d_shim.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ROWS 25
#define CIRCLES 200
#define STEPS 600

int main( int argc, char** argv )
{
	int steps = argc > 1 ? atoi( argv[1] ) : STEPS;
	int workers = argc > 2 ? atoi( argv[2] ) : 0; // 0 workers: single threaded
	pb2_world_create( 0.0f, -10.0f, workers );
	uint32_t rows[32];
	for ( int i = 0; i < 32; i++ ) rows[i] = 0xFFFFFFFFu;
	pb2_world_set_layer_matrix( rows );

	int n = 0;
	uint32_t bodies[ROWS * ( ROWS + 1 ) / 2 + CIRCLES + 1];
	uint32_t ground = pb2_body_create( PB2_BODY_STATIC, 0.0f, -0.5f, 0.0f, n, 1.0f, 0.0f, 0.0f, 0 );
	pb2_shape_create_box( ground, 0, 0, 100.0f, 0.5f, 0, 0, 0, 0, 1.0f, 0.6f, 0.0f, 0 );
	bodies[n++] = ground;

	for ( int r = 0; r < ROWS; r++ )
		for ( int c = 0; c < ROWS - r; c++ )
		{
			float x = ( c - ( ROWS - r - 1 ) * 0.5f ) * 1.05f, y = 0.5f + r * 1.0f;
			uint32_t b = pb2_body_create( PB2_BODY_DYNAMIC, x, y, 0.0f, n, 1.0f, 0.0f, 0.0f, 0 );
			pb2_shape_create_box( b, n, 0, 0.5f, 0.5f, 0, 0, 0, 0, 1.0f, 0.6f, 0.0f, 0 );
			bodies[n++] = b;
		}
	for ( int i = 0; i < CIRCLES; i++ )
	{
		float x = ( ( i * 37 ) % 41 - 20 ) * 0.4f, y = ROWS + 3.0f + i * 0.9f; // deterministic scatter
		uint32_t b = pb2_body_create( PB2_BODY_DYNAMIC, x, y, 0.0f, n, 1.0f, 0.0f, 0.0f, 0 );
		pb2_shape_create_circle( b, n, 0, 0, 0, 0.35f, 1.0f, 0.4f, 0.2f, 0 );
		bodies[n++] = b;
	}

	PB2StepInfo info;
	long contacts = 0;
	for ( int s = 0; s < steps; s++ )
	{
		pb2_step( 1.0f / 60.0f, 4, &info );
		contacts += info.contactCount;
	}

	uint64_t h = 1469598103934665603ull;
	for ( int i = 0; i < n; i++ )
	{
		float st[10];
		pb2_body_get_state( bodies[i], st );
		for ( int k = 0; k < 10; k++ )
		{
			uint32_t bits;
			memcpy( &bits, &st[k], 4 );
			h = ( h ^ bits ) * 1099511628211ull;
		}
	}
	printf( "bodies=%d steps=%d contact_events=%ld hash=%016llx\n", n, steps, contacts, (unsigned long long)h );
	pb2_world_destroy();
	return 0;
}
