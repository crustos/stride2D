// Draw2D: the renderer with no physics, to see it work. A box, a ring of discs, two overlapping translucent discs and a texture-mapped triangle, animated by
// a frame counter. The same source is:
//   native   python3 tools/player_build.py gfx_samples/Draw2D --run      opens a window (or draws offscreen with no display; STRIDE2D_GFX=soft|gl picks the backend)
//   browser  python3 tools/player_build.py gfx_samples/Draw2D --web      writes build/player/Draw2D-web/: serve it and open index.html (?gfx=webgl2 or ?gfx=webgpu)
// It is not in samples/, because `build.py test` runs those on .NET and compares the output, and a picture is not text.
using System;
using Stride2D.Native.Gfx2D;

static class Game
{
    const int Discs = 12;
    static float[] sprites;
    static float[] tri;
    static int tex;
    static int frame;

    // Called once. Returns 0 when it is ready.
    public static int Init()
    {
        if (GFX.Init(640, 360) == 0) return 1;
        GFX.Camera(0f, 0f, 5f, 0.08f, 0.09f, 0.12f);          // looks at (0,0), 10 world units high, a dark blue background
        sprites = new float[(Discs + 3) * GFX.SpriteFloats];
        tri = new float[3 * GFX.MeshVertexFloats];
        byte[] px = new byte[4 * 4 * 4];                       // a 4x4 checkerboard
        for (int y = 0; y < 4; y++)
        {
            for (int x = 0; x < 4; x++)
            {
                int i = (y * 4 + x) * 4;
                byte v = (byte)(((x + y) & 1) == 0 ? 255 : 90);
                px[i] = v; px[i + 1] = v; px[i + 2] = 255; px[i + 3] = 255;
            }
        }
        tex = GFX.Texture(4, 4, GFX.FilterNearest, px);
        frame = 0;
        return 0;
    }

    static void Sprite(int n, float x, float y, float hw, float hh, float angle, float r, float g, float b, float a, int shape, int layer)
    {
        int o = n * GFX.SpriteFloats;
        sprites[o] = x; sprites[o + 1] = y; sprites[o + 2] = hw; sprites[o + 3] = hh; sprites[o + 4] = angle;
        sprites[o + 5] = r; sprites[o + 6] = g; sprites[o + 7] = b; sprites[o + 8] = a;
        sprites[o + 9] = (float)shape; sprites[o + 10] = (float)layer; sprites[o + 11] = 0f;
    }

    static void Vertex(int n, float x, float y, float u, float v)
    {
        int o = n * GFX.MeshVertexFloats;
        tri[o] = x; tri[o + 1] = y; tri[o + 2] = u; tri[o + 3] = v;
        tri[o + 4] = 1f; tri[o + 5] = 1f; tri[o + 6] = 1f; tri[o + 7] = 1f;
    }

    // Draws one frame. Returns 0 when the window was closed.
    public static int Step()
    {
        float t = frame * 0.02f;
        int n = 0;
        Sprite(n++, 0f, 0f, 2.2f, 1.2f, t * 0.5f, 0.9f, 0.55f, 0.15f, 1f, GFX.ShapeBox, 1);
        for (int i = 0; i < Discs; i++)
        {
            float a = t + i * 6.2831853f / Discs;
            float k = (float)i / Discs;
            Sprite(n++, MathF.Cos(a) * 3.4f, MathF.Sin(a) * 3.4f, 0.4f, 0.4f, 0f, 0.2f + 0.8f * k, 0.8f - 0.5f * k, 0.9f, 1f, GFX.ShapeDisc, 2);
        }
        Sprite(n++, -0.5f, 0.2f, 0.9f, 0.9f, 0f, 1f, 0.2f, 0.2f, 0.6f, GFX.ShapeDisc, 3);       // the two translucent ones overlap
        Sprite(n++, 0.5f, -0.2f, 0.9f, 0.9f, 0f, 0.2f, 1f, 0.2f, 0.6f, GFX.ShapeDisc, 3);
        Vertex(0, -4.5f, -4f, 0f, 0f);
        Vertex(1, -2.5f, -4f, 1f, 0f);
        Vertex(2, -3.5f, -2.2f, 0.5f, 1f);

        GFX.Begin();
        GFX.Sprites(sprites, n);
        GFX.Triangles(tri, 3, tex);
        int open = GFX.End();
        frame++;
        return open;
    }

    // The page's two entry points (tools/player_build.py --web): Init() once, then Frame() every animation frame.
    public static void Frame() { Step(); }

    // Native: runs until the window is closed (or, with no window, 600 frames).
    public static int Main()
    {
        if (Init() != 0)
        {
            Console.WriteLine("Draw2D: no renderer");
            return 1;
        }
        Console.WriteLine("backend " + GFX.Backend());
        while (Step() != 0 && frame < 600) { }
        Console.WriteLine("frames " + frame + " hash " + GFX.FrameHash());
        GFX.Shutdown();
        return 0;
    }
}
