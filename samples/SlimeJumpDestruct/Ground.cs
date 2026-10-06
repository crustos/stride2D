using System;
using Stride2D;
using Stride2D.Terrain;

// The level's diggable ground: one TerrainLayer, a pixel bitmap whose solid pixels are the physics shapes.
//
// The physics world cannot see it through its queries: a terrain shape belongs to no collider (its collider index is -1), so OverlapBox and
// Raycast skip it. The player, the bot, the enemies, the bullets and the lasso all sense the world with those queries, so everything here that
// is a question about a wall goes through Ground.Overlap and Ground.Ray instead: they ask the physics world (the bedrock boxes, the climbable
// walls) and the pixels (the terrain), and answer with the nearer. The pixels are also the truth the shapes are built from, so the two agree.
static class Ground
{
    public const int TerrainHit = 1073741823;       // what Ray returns when the nearest thing is terrain (an index that no collider has)
    public const float PixelsPerUnit = 8f;
    const int SmallRadius = 5;                       // pixels: a bullet's crater is 10 pixels across
    const int BigRadius = 8;                        // a dying enemy's: a unit in radius

    public static float HitX;                        // the last Ray's hit: point, normal, distance
    public static float HitY;
    public static float HitNX;
    public static float HitNY;
    public static float HitDistance;
    public static int Craters;                       // how many times the ground was dug, and how many chunks that rebuilt
    public static int ChunksRebuilt;

    static TerrainLayer layer;
    static Shape small;
    static Shape big;
    static float originX;
    static float originY;
    static uint wallBit;

    // Makes the layer; Add() fills it and Build() makes its shapes. widthUnits x heightUnits is its size in world units, from (x, y).
    public static void Init(Scene2D scene, float x, float y, int widthUnits, int heightUnits)
    {
        int w = widthUnits * 8;
        int h = heightUnits * 8;
        originX = x;
        originY = y;
        wallBit = 1u << Layers.Wall;
        layer = new TerrainLayer(scene, w, h, widthUnits / 8, heightUnits / 4, PixelsPerUnit, x, y, TerrainLayer.Chains);
        layer.PhysicsLayer = Layers.Wall;
        layer.Friction = 0f;                         // the slime must not catch on the ground
        small = Shape.GenerateShapeCircle(SmallRadius);
        big = Shape.GenerateShapeCircle(BigRadius);
    }

    // A solid rectangle of ground, in world units (whole units: the bitmap is 8 pixels to the unit).
    public static void Add(float x, float y, float w, float h, int r, int g, int b)
    {
        int x0 = (int)((x - originX) * PixelsPerUnit + 0.5f);
        int y0 = (int)((y - originY) * PixelsPerUnit + 0.5f);
        int x1 = (int)((x + w - originX) * PixelsPerUnit + 0.5f);
        int y1 = (int)((y + h - originY) * PixelsPerUnit + 0.5f);
        for (int px = x0; px < x1; px++)
            for (int py = y0; py < y1; py++)
            {
                // a little grain so a renderer has something to show: the colour varies by a few levels from pixel to pixel
                int k = ((px * 7 + py * 13) & 7) * 2;
                layer.SetPixel(px, py, r + k, g + k, b + k, 255);
            }
    }

    public static bool Build() { return layer.Build(); }
    public static bool Ok() { return layer != null && layer.Ok; }
    public static int ShapeCount() { return layer.ShapeCount; }

    // Rebuilds the shapes of the chunks that were dug since the last step. Call it once a step, before the physics steps.
    public static void Update()
    {
        if (layer == null) return;
        ChunksRebuilt += layer.Update();
    }

    public static void Destroy() { if (layer != null) layer.Destroy(); }

    // ---- digging ----------------------------------------------------------------------------------------------------------------

    // Clears a disc of ground centred on the world point. True if any ground was there.
    public static bool Dig(float wx, float wy, bool large)
    {
        if (layer == null || !layer.Ok) return false;
        int px = PixelX(wx);
        int py = PixelY(wy);
        int r = SmallRadius;
        Shape s = small;
        if (large) { r = BigRadius; s = big; }
        bool changed = layer.Paint(s, px - r, py - r, true, 0, 0, 0);
        if (changed) Craters++;
        return changed;
    }

    public static int SolidPixels()
    {
        int n = 0;
        for (int y = 0; y < layer.Height; y++)
            for (int x = 0; x < layer.Width; x++)
                if (layer.IsSolid(x, y)) n++;
        return n;
    }

    // ---- queries (what the physics world's OverlapBox and Raycast do not see) ---------------------------------------------------

    static int PixelX(float wx) { float f = (wx - originX) * PixelsPerUnit; if (f < 0f) return -1; return (int)f; }
    static int PixelY(float wy) { float f = (wy - originY) * PixelsPerUnit; if (f < 0f) return -1; return (int)f; }
    static bool SolidAt(float wx, float wy) { return layer.IsSolid(PixelX(wx), PixelY(wy)); }

    // Is any pixel under the box solid?
    static bool TerrainBox(float x0, float y0, float x1, float y1)
    {
        int px0 = PixelX(x0);
        int px1 = PixelX(x1);
        int py0 = PixelY(y0);
        int py1 = PixelY(y1);
        for (int px = px0; px <= px1; px++)
            for (int py = py0; py <= py1; py++)
                if (layer.IsSolid(px, py)) return true;
        return false;
    }

    // Sim.OverlapBox(...) > 0, and the terrain too if the mask has the Wall layer.
    public static bool Overlap(Scene2D scene, float cx, float cy, float halfW, float halfH, uint mask)
    {
        if (scene.Physics.Sim.OverlapBox(cx, cy, halfW, halfH, 0f, mask, false) > 0) return true;
        if ((mask & wallBit) == 0u || layer == null || !layer.Ok) return false;
        return TerrainBox(cx - halfW, cy - halfH, cx + halfW, cy + halfH);
    }

    static int S(int px, int py)
    {
        if (layer.IsSolid(px, py)) return 1;
        return 0;
    }

    // Sim.Raycast(...) with the terrain: the collider index of the nearest hit, TerrainHit if that is the terrain, -1 for nothing. The point, normal
    // and distance are in Hit*. The terrain is found by marching the ray half a pixel at a time, then bisecting the last step.
    public static int Ray(Scene2D scene, float ox, float oy, float dx, float dy, float maxDistance, uint mask)
    {
        int found = scene.Physics.Sim.Raycast(ox, oy, dx, dy, maxDistance, mask, false);
        float best = maxDistance + 1f;
        if (found >= 0)
        {
            best = scene.Physics.Sim.HitDistance;
            HitX = scene.Physics.Sim.HitX;
            HitY = scene.Physics.Sim.HitY;
            HitNX = scene.Physics.Sim.HitNX;
            HitNY = scene.Physics.Sim.HitNY;
            HitDistance = best;
        }
        if ((mask & wallBit) == 0u || layer == null || !layer.Ok) return found;
        float step = 0.5f / PixelsPerUnit;
        float t = 0f;
        while (t <= maxDistance && t < best)
        {
            if (SolidAt(ox + dx * t, oy + dy * t))
            {
                float lo = t - step;                  // air (or the start), hi is solid
                float hi = t;
                if (lo < 0f) lo = 0f;
                for (int i = 0; i < 6; i++)
                {
                    float mid = (lo + hi) * 0.5f;
                    if (SolidAt(ox + dx * mid, oy + dy * mid)) hi = mid; else lo = mid;
                }
                if (hi >= best) return found;         // the physics world's hit is nearer
                int px = PixelX(ox + dx * hi);
                int py = PixelY(oy + dy * hi);
                float nx = 0f;
                float ny = 0f;
                for (int k = -1; k <= 1; k++)
                {
                    nx += S(px - 1, py + k) - S(px + 1, py + k);
                    ny += S(px + k, py - 1) - S(px + k, py + 1);
                }
                float nl = MathF.Sqrt(nx * nx + ny * ny);
                if (nl < 0.0001f) { nx = -dx; ny = -dy; }
                else { nx /= nl; ny /= nl; }
                HitX = ox + dx * hi;
                HitY = oy + dy * hi;
                HitNX = nx;
                HitNY = ny;
                HitDistance = hi;
                return TerrainHit;
            }
            t += step;
        }
        return found;
    }
}
