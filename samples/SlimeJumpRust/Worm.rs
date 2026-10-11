// A worm (tag 2): crawls back and forth around where it starts. Touch it from the side and the slime is hurt; land on it and it is squashed; a bullet (which sets its tag to 5) kills it.
use stride2d::*;

const DT: f32 = 0.016666668;

#[script(max_instances = 8)]
struct Worm {
    node: i32,
    home: f32,
    dir: f32,
}

impl Worm {
    fn start(&mut self) {
        self.home = node_x(self.node);
        self.dir = 1.0;
        set_tag(self.node, 2);
    }

    fn fixed_update(&mut self) {
        if get_tag(self.node) == 5 {
            destroy_node(self.node);
            return;
        }
        let mut x: f32 = node_x(self.node);
        x += self.dir * 2.0 * DT;
        if x > self.home + 3.0 { self.dir = -1.0; }
        if x < self.home - 3.0 { self.dir = 1.0; }
        set_pos(self.node, x, node_y(self.node));
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - x;
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -0.8 && dx < 0.8 && dy > -0.8 && dy < 0.8 {
            if dy > 0.35 && velocity_y(s) < 0.0 {
                set_velocity(s, velocity_x(s), 11.0);       // squashed: the slime bounces off
                destroy_node(self.node);
            } else {
                set_tag(s, 3);
            }
        }
    }
}
