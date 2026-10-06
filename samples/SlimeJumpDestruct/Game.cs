// SlimeJumpDestruct: SlimeJump with ground you can dig and enemies that burst. The level's walls are a terrain (src/terrain): the bot's bullets dig
// craters where they hit it, and an enemy that dies is shattered (src/destruction) into pieces that fall into the pit it leaves. The rest is SlimeJump.
using System;
using Stride2D;
using Stride2D.Native.Box2D;
using Stride2D.Terrain;

static class Game
{
    const int MaxFrames = 3000;
    static int failures = 0;

    static void Check(bool ok, string what)
    {
        if (ok) return;
        failures++;
        Console.WriteLine("FAIL " + what);
    }

    static int Milli(float v) { return (int)(v * 1000f); }

    static Collider2D MakeCollider(Scene2D scene, Node n, float w, float h, bool trigger, float offY)
    {
        Collider2D c = scene.NewBoxCollider(n, w, h);
        c.Friction = 0f;
        c.IsTrigger = trigger;
        c.OffsetY = offY;
        scene.Finish(c.Self);
        return c;
    }

    static Node MakeBox(Scene2D scene, float x, float y, float w, float h, int layer, int tag, bool trigger, float offY)
    {
        Node n = scene.NewNode(null);
        n.SetPosition(x, y);
        n.Layer = layer;
        n.Tag = tag;
        MakeCollider(scene, n, w, h, trigger, offY);
        return n;
    }

    public static int Main()
    {
        Scripts.Init();
        Scene2D scene = new Scene2D();
        scene.FixedDeltaTime = Cfg.Dt;
        scene.SetGravity(0f, Cfg.Gravity);
        Level.Init();
        uint[] layerRows = Level.LayerRows();
        scene.Physics.Sim.SetLayerMatrix(layerRows);

        // the walls: bedrock stays physics boxes; the rest is one terrain, a bitmap of 8 pixels to the unit that bullets dig into
        Ground.Init(scene, 0f, 2f, 64, 12);
        for (int i = 0; i < Level.WallCount; i++)
        {
            if (Level.WallDiggable(i))
                Ground.Add(Level.Wall(i, 0), Level.Wall(i, 1), Level.Wall(i, 2), Level.Wall(i, 3), 110, 85, 60);
            else
                MakeBox(scene, Level.Wall(i, 0) + Level.Wall(i, 2) * 0.5f, Level.Wall(i, 1) + Level.Wall(i, 3) * 0.5f,
                        Level.Wall(i, 2), Level.Wall(i, 3), Layers.Wall, Shared.TagWall, false, 0f);
        }
        Ground.Build();
        int groundPixels = Ground.SolidPixels();
        Console.WriteLine("terrain built=" + (Ground.Ok() ? 1 : 0) + " pixels=" + groundPixels + " shapes=" + Ground.ShapeCount());
        Debris.Init(scene);
        for (int i = 0; i < Level.ClimbCount; i++)
            MakeBox(scene, Level.Climb(i, 0) + Level.Climb(i, 2) * 0.5f, Level.Climb(i, 1) + Level.Climb(i, 3) * 0.5f,
                    Level.Climb(i, 2), Level.Climb(i, 3), Layers.Climbable, Shared.TagWall, false, 0f);
        for (int i = 0; i < Level.SpikeCount; i++)
        {
            float sw = Level.Spike(i, 2);
            float sh = Level.Spike(i, 3);
            Node n = MakeBox(scene, Level.Spike(i, 0) + sw * 0.5f, Level.Spike(i, 1) + sh * 0.5f, sw, sh * 0.6f, Layers.Hazard, Shared.TagHazard, true, -sh * 0.2f);
            Scripts.AddHazardScript(n);
        }
        Shared.InitSaves(Level.SaveCount);
        for (int i = 0; i < Level.SaveCount; i++)
        {
            float sx = Level.Save(i, 0);
            float sy = Level.Save(i, 1);
            Node n = MakeBox(scene, sx, sy, 1.2f, 1.4f, Layers.Gem, Shared.TagSavePoint, true, 0.7f);
            SavePointScript sp = Scripts.AddSavePointScript(n);
            sp.X = sx;
            sp.Y = sy + Cfg.ColliderH * 0.5f + 0.2f;
            sp.Index = i;
        }
        Shared.InitGems(Level.GemCount);
        for (int i = 0; i < Level.GemCount; i++)
        {
            Node n = scene.NewNode(null);
            n.SetPosition(Level.Gem(i, 0), Level.Gem(i, 1));
            n.Layer = Layers.Gem;
            n.Tag = Shared.TagGem;
            Collider2D gc = scene.NewCircleCollider(n, 0.45f);
            gc.IsTrigger = true;
            scene.Finish(gc.Self);
            GemScript gs = Scripts.AddGemScript(n);
            gs.Index = i;
            Shared.RegisterGem(i, n);
        }
        Shared.InitCrumbly(Level.CrumblyCount);
        for (int i = 0; i < Level.CrumblyCount; i++)
        {
            // each collider is 0.04 wider than its tile, so neighbours overlap: with exactly flush boxes the slime catches on the seam (a ghost collision)
            Node cn = MakeBox(scene, Level.CrumblyTile(i, 0) + 0.5f, Level.CrumblyTile(i, 1) + 0.5f, Level.CrumblyTile(i, 2) + 0.04f, Level.CrumblyTile(i, 3), Layers.Wall, Shared.TagWall, false, 0f);
            CrumblyScript cs = Scripts.AddCrumblyScript(cn);
            cs.Index = i;
            Shared.RegisterCrumbly(i, cn);
        }
        for (int i = 0; i < Level.ShooterCount; i++)
        {
            // the shooter's tile is already part of the walls: this node only carries the trap
            Node sn = scene.NewNode(null);
            sn.SetPosition(Level.Shooter(i, 0), Level.Shooter(i, 1));
            ShooterScript ss = Scripts.AddShooterScript(sn);
            ss.DirX = Level.Shooter(i, 2);
            ss.DirY = Level.Shooter(i, 3);
        }
        Shared.InitEnemies(Level.EnemyCount);
        for (int i = 0; i < Level.EnemyCount; i++)
        {
            int kind = Level.EnemyKind(i);
            float ex = Level.EnemyX(i);
            float ey = Level.EnemyY(i);
            Node en = scene.NewNode(null);
            en.SetPosition(ex, ey);
            en.Layer = Layers.Enemy;
            en.Tag = Shared.TagEnemyBase + i;
            Rigidbody2D erb = scene.NewRigidbody(en, PB2.BodyDynamic);
            erb.GravityScale = EnemyCfg.GravityScale(kind);
            erb.LinearDamping = 0f;
            erb.FreezeRotation = true;
            erb.CanSleep = false;
            scene.Finish(erb.Self);
            MakeCollider(scene, en, EnemyCfg.ColliderW(kind), EnemyCfg.ColliderH(kind), false, 0f);
            EnemyScript es = Scripts.AddEnemyScript(en);
            es.Index = i;
            es.Kind = kind;
            es.InitX = ex;
            es.InitY = ey;
            Shared.RegisterEnemy(i, en, kind, ex, ey);
        }
        Node goal = MakeBox(scene, Level.GoalX(), Level.GoalY(), 1.4f, 2f, Layers.Gem, Shared.TagGoal, true, 0f);
        Scripts.AddGoalScript(goal);

        // the player: a dynamic box; gravity is applied by PlayerScript
        Node player = scene.NewNode(null);
        player.SetPosition(Level.SpawnX(), Level.SpawnY());
        player.Layer = Layers.Player;
        player.Tag = Shared.TagPlayer;
        Rigidbody2D rb = scene.NewRigidbody(player, PB2.BodyDynamic);
        rb.GravityScale = 0f;
        rb.LinearDamping = Cfg.LinearDamping;
        rb.FreezeRotation = true;
        rb.IsBullet = true;
        rb.CanSleep = false;
        scene.Finish(rb.Self);
        Collider2D playerCol = MakeCollider(scene, player, Cfg.ColliderW, Cfg.ColliderH, false, 0f);
        Shared.PlayerColliderIndex = playerCol.ColliderIndex;
        Scripts.AddPlayerScript(player);
        Scripts.AddLassoScript(player);
        Scripts.AddBotScript(player);

        // The terrain's queries, checked before the run. A pocket is dug deep inside the tower, off the route, and asked about; then a player's bullet is
        // fired inside it at the wall, and digs the pocket wider where it hits (counted at the end).
        uint wallMask = (1u << Layers.Wall) | (1u << Layers.Climbable);
        bool solidBefore = Ground.Overlap(scene, 62f, 8f, 0.1f, 0.1f, wallMask);
        Ground.Dig(62f, 8f, true);
        Ground.Update();
        bool solidAfter = Ground.Overlap(scene, 62f, 8f, 0.1f, 0.1f, wallMask);
        int rayHit = Ground.Ray(scene, 62f, 8f, 1f, 0f, 3f, wallMask);
        float rayDist = Ground.HitDistance;
        float rayNX = Ground.HitNX;
        Console.WriteLine("pocket: solid before=" + (solidBefore ? 1 : 0) + " after=" + (solidAfter ? 1 : 0) + " ray hit terrain=" + (rayHit == Ground.TerrainHit ? 1 : 0) + " distance*1000=" + Milli(rayDist) + " normal x*1000=" + Milli(rayNX));
        Check(solidBefore && !solidAfter, "digging cleared the ground at the point");
        Check(rayHit == Ground.TerrainHit && rayDist > 0.85f && rayDist < 1.15f && rayNX < -0.7f, "a ray from the pocket hits its wall about a unit away, facing back");
        int cratersBefore = Ground.Craters;
        BulletScript.Spawn(62f, 8f, Cfg.BulletSpeed, 0f, Cfg.BulletDamage, Cfg.BulletLifetime, true);

        int wonFrame = -1;
        int firstClimb = -1;
        int firstJump = -1;
        float maxX = Level.SpawnX();
        float maxY = Level.SpawnY();
        for (int frame = 0; frame < MaxFrames && !Shared.Won; frame++)
        {
            Ground.Update();                         // rebuild the chunks that were dug during the last step
            Scripts.Tick(scene, Cfg.Dt);
            float px = player.WorldX();
            float py = player.WorldY();
            if (px > maxX) maxX = px;
            if (py > maxY) maxY = py;
            if (Shared.PlayerClimbing && firstClimb < 0) firstClimb = frame;
            if (Shared.PlayerJumping && firstJump < 0) firstJump = frame;
            if (Shared.LassoActive && frame % 10 == 0)
            {
                int att = 0;
                if (Shared.LassoAttached) att = 1;
                Console.WriteLine("lasso t=" + frame + " attached=" + att + " len*1000=" + Milli(Shared.LassoLength) + " x*1000=" + Milli(px) + " y*1000=" + Milli(py));
            }
            if (frame % 100 == 0)
            {
                string line = "t=" + (frame / 100) + "s x*1000=" + Milli(px) + " y*1000=" + Milli(py);
                Console.WriteLine(line);
            }
            if (Shared.Won) wonFrame = frame;
        }
        int won = 0;
        if (Shared.Won) won = 1;
        int slain = 0;
        for (int i = 0; i < Shared.EnemyCount(); i++)
            if (!Shared.EnemyAlive(i)) slain++;
        Console.WriteLine("won=" + won + " frame=" + wonFrame + " deaths=" + Shared.Deaths + " gems=" + Shared.Gems + " enemies=" + Shared.EnemyCount() + " slain=" + slain + " crumbled=" + Shared.CrumbledCount());
        Console.WriteLine("terrain: craters=" + Ground.Craters + " chunks rebuilt=" + Ground.ChunksRebuilt + " pixels dug=" + (groundPixels - Ground.SolidPixels()) + " shapes=" + Ground.ShapeCount());
        Console.WriteLine("debris: enemies shattered=" + Debris.Shatters + " pieces=" + Debris.Shards + " pieces still there=" + Debris.Live(scene));
        int problems = scene.Validate();
        Console.WriteLine("scene problems=" + problems);
        Check(Ground.Craters > cratersBefore + 1, "the bullet fired in the pocket dug the ground where it hit (and the enemies' pits)");
        Check(Debris.Shatters == 2 && Debris.Shards > 4, "both enemies shattered into pieces");
        Console.WriteLine("first jump frame=" + firstJump + " first climb frame=" + firstClimb);
        Console.WriteLine("max x*1000=" + Milli(maxX) + " max y*1000=" + Milli(maxY) + " end x*1000=" + Milli(player.WorldX()) + " y*1000=" + Milli(player.WorldY()));
        Ground.Destroy();
        if (failures == 0) Console.WriteLine("all checks passed");
        else Console.WriteLine("FAILURES: " + failures);
        return won == 1 && problems == 0 && failures == 0 ? 0 : 1;
    }
}
