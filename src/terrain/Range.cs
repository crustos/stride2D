// Stride2D.Terrain. Ported from DTerrain (MIT, (c) 2020 Dominik Zimny); see LICENSE.md.

namespace Stride2D.Terrain
{
    ///<summary>
    ///Range represents a single range: [min;max]
    ///
    ///A struct: two ints, no heap allocation per range. Equality is by value (Min and Max),
    ///which is what Column.RemoveEqual relies on.
    ///</summary>
    public struct Range
    {
        public int Min;
        public int Max;

        public int Length { 
            get
            {
                int len = Calc.Abs(Max - Min);
                if (len <= 0) return 0;
                else return len;
            } 
        }

        public bool isWithin(int point)
        {
            return point <= Max && point >= Min;
        }

        public Range(int a, int b)
        {
            Min = a;
            Max = b;
        }

        public bool Equals(Range r)
        {
            return (Min == r.Min) && (Max == r.Max);
        }

        /// <summary>This range moved by a rows (negative: down).</summary>
        public Range Shifted(int a)
        {
            return new Range(Min + a, Max + a);
        }
    }
}
