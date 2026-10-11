// The goal flag: when the slime reaches it, its tag becomes 99 and the globals say so (the editor and the tests look at that).
use stride2d::*;

#[script(max_instances = 1)]
struct Goal {
    node: i32,
}

impl Goal {
    fn start(&mut self) {
        set_tag(self.node, 8);
    }

    fn fixed_update(&mut self) {
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - node_x(self.node);
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -0.8 && dx < 0.8 && dy > -0.8 && dy < 0.8 {
            set_tag(self.node, 99);
            set_global(5, 1.0);
        }
    }
}
