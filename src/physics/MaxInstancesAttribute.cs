// Stride2D. Derived from the Prowl Game Engine (MIT, (c) Michael Sakharov); see LICENSE.md.

using System;

// In the GLOBAL namespace on purpose, as unity_pack's is: a script is written against the engine, and should not need `using Stride2D.Physics;`
// (an engine-internal namespace) to say how many of it there can be.

/// <summary>
/// Marks an ARENA class: C#'s own reference semantics (null, aliasing, <c>==</c>, a reference stored in a field) from a fixed number of
/// statically allocated slots, which is what lets the code be translated to C (see tools/ccsharp). Under .NET it does nothing, and the
/// class is an ordinary one; CCSharp reads the capacity from it. The capacity is the most objects of this class that can ever exist, so it
/// is also the most memory the class can ever occupy: <c>capacity x sizeof</c>, which is what keeps the data of a small simulation inside
/// the CPU cache. <c>python3 build.py arenas</c> prints that figure for every arena class.
/// </summary>
[AttributeUsage(AttributeTargets.Class)]
internal sealed class MaxInstancesAttribute : Attribute
{
    public MaxInstancesAttribute(int capacity) { Capacity = capacity; }
    public int Capacity { get; }
}
