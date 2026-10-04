// Stride2D. Derived from the Prowl Game Engine (MIT, (c) Michael Sakharov); see LICENSE.md.

namespace Stride2D.Physics;

/// <summary>
/// What the simulation keeps for one body: its pose history, written straight from the step's move events. This used to live in the
/// managed Rigidbody2D, reached through an interface call for every moving body on every step; here the poses of all the bodies sit in
/// one small arena, so the step's write loop and the render-time read loop walk contiguous memory.
/// <para/>
/// An arena class: at most <see cref="PhysicsLimits.Bodies"/> exist at once, recycled by <see cref="Registry2D"/>. Fields are plain
/// numbers on purpose: every byte here is multiplied by the capacity.
/// </summary>
[MaxInstances(PhysicsLimits.Bodies)]
internal sealed class BodyRecord
{
    public int Index;            // the slot: what the native layer calls this body
    public uint Native;          // the native body, 0 while there is none
    public bool Asleep;          // the last move event said the body fell asleep, and it has not moved since
    public BodyPose2D Pose;      // the last two simulated poses

    /// <summary>A step moved this body.</summary>
    public void Moved(float x, float y, float cos, float sin, bool fellAsleep, int step)
    {
        Pose.Push(x, y, cos, sin, step);
        Asleep = fellAsleep;
    }

    /// <summary>Back to a new body's state, for a recycled slot.</summary>
    public void Reset(int index)
    {
        Index = index;
        Native = 0;
        Asleep = false;
        BodyPose2D fresh = new BodyPose2D();
        Pose = fresh;
    }
}
