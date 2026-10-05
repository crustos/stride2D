// HybridScripts: Headless2D, with a script that is outside the Crust subset: it uses a lambda and try/catch.
//
// Built the plain way (python3 build.py player samples/HybridScripts) that is refused. With --dna the script runs on DotNetAnywhere, and so do the
// classes that use it (the generated Scripts sink, and Main); the engine -- the scene, the physics, Box2D -- stays native, and the managed side
// reaches its objects (Node, Component, Collision2D ...) by address. The same source also runs on .NET, and prints the same.
using System;
using Stride2D;
using Stride2D.Native.Box2D;

[Script, MaxInstances(4)]
class Spinner
{
    public Component Self;
    public int Hits;
    public int Score;
    public int Frames;
    public int Caught;

    public void Reset() { Hits = 0; Score = 0; Frames = 0; Caught = 0; }

    public void OnCollisionBegin2D(Collision2D hit)
    {
        Hits++;
        Func<int, int> weight = n => n * 10 + (int)(hit.NY * -100f);      // a lambda: not in the Crust subset
        Score += weight(Hits);
        Console.WriteLine("hit " + Hits + " score " + Score + " normalY*1000=" + (int)(hit.NY * 1000f));
    }

    public void Update()
    {
        Frames++;
        try
        {
            if (Frames % 100 == 0) throw new InvalidOperationException("tick " + Frames);   // try/catch: not in the Crust subset either
        }
        catch (InvalidOperationException e)
        {
            Caught++;
            Console.WriteLine("caught: " + e.Message);
        }
    }
}

static class Game
{
    public static int Main()
    {
        Scripts.Init();
        Scene2D scene = new Scene2D();

        Node ground = scene.NewNode(null);
        ground.SetPosition(0f, -0.5f);
        scene.AddBoxCollider(ground, 100f, 1f);

        Node ball = scene.NewNode(null);
        ball.SetPosition(0f, 5f);
        scene.AddRigidbody(ball, PB2.BodyDynamic);
        scene.AddCircleCollider(ball, 0.5f);
        Spinner script = Scripts.AddSpinner(ball);

        for (int frame = 0; frame < 240; frame++)
        {
            Scripts.Tick(scene, 1f / 60f);
            if (frame % 60 == 0)
                Console.WriteLine("frame " + frame + " y*1000=" + (int)(ball.WorldY() * 1000f));
        }
        int rest = (int)(ball.WorldY() * 1000f);
        Console.WriteLine("rest y*1000=" + rest + " hits=" + script.Hits + " score=" + script.Score + " frames=" + script.Frames + " caught=" + script.Caught);
        return (rest > 450 && rest < 550 && script.Hits >= 1 && script.Caught == 2) ? 0 : 1;
    }
}
