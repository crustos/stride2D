using System;
using Stride2D;
using Stride2D.Native.Box2D;
using Stride2D.Destruction;

// What is left of an enemy: when one dies, a body the size of its collider is shattered into pieces (src/destruction) that fall to the ground and
// pile up there until the player respawns. The enemy's own node is not the one shattered: it is only switched off, and comes back when the player
// does (Shared.ResetEnemies), so a stand-in is made at its place and shattered instead.
static class Debris
{
    public static int Shards;                        // pieces made so far
    public static int Shatters;                      // enemies shattered so far
    static Destruction2D boom;
    static ExplodeOptions opt;

    public static void Init(Scene2D scene)
    {
        boom = new Destruction2D(scene, 20240607u);
        opt = new ExplodeOptions();
        opt.Mode = Fracturer.Voronoi;
        opt.ExtraPoints = 3;
        opt.FragmentLayer = Layers.Debris;
        opt.RenderLayer = 4;
    }

    // pushX, pushY: the direction of the bullet that killed it (the pieces are thrown that way too).
    public static void Shatter(Scene2D scene, int kind, float x, float y, float pushX, float pushY)
    {
        Node corpse = scene.NewNode(null);
        if (corpse == null) return;
        corpse.SetPosition(x, y);
        corpse.Layer = Layers.Debris;
        Rigidbody2D rb = scene.AddRigidbody(corpse, PB2.BodyDynamic);
        Collider2D col = scene.AddBoxCollider(corpse, EnemyCfg.ColliderW(kind), EnemyCfg.ColliderH(kind));
        if (rb == null || col == null)
        {
            scene.Destroy(corpse);
            return;
        }
        if (EnemyCfg.IsFlying(kind)) { opt.R = 0.65f; opt.G = 0.35f; opt.B = 0.85f; }
        else { opt.R = 0.45f; opt.G = 0.8f; opt.B = 0.3f; }
        int n = boom.Explode(corpse, opt);
        if (n == 0)
        {
            scene.Destroy(corpse);
            return;
        }
        Shatters++;
        Shards += n;
        for (int i = 0; i < n; i++)
        {
            Node f = boom.Fragments[i];
            f.Tag = Shared.TagDebris;
            Component rc = scene.Find(f, ComponentKind.Rigidbody2D);
            rc.Body.SetVelocity(pushX * 0.15f + (Shared.Rand01() - 0.5f) * 4f, MathF.Abs(pushY) * 0.1f + 2f + Shared.Rand01() * 4f);
        }
    }

    public static int Live(Scene2D scene)
    {
        int n = 0;
        for (int i = 0; i < scene.NodeHighWater; i++)
        {
            Node b = scene.NodeAt(i);
            if (b != null && b.Alive && !b.Destroyed && b.Tag == Shared.TagDebris) n++;
        }
        return n;
    }
}
