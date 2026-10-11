// A checkpoint flag: the first time the slime comes by, it is where the slime comes back to after a fall or a hurt. Gems picked up until then are kept.
use stride2d::*;

#[script(max_instances = 8)]
struct Save {
    node: i32,
    used: i32,
}

impl Save {
    fn fixed_update(&mut self) {
        if self.used != 0 { return; }
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - node_x(self.node);
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -1.0 && dx < 1.0 && dy > -1.0 && dy < 1.0 && get_tag(s) == 1 {
            self.used = 1;
            set_global(2, node_x(self.node));
            set_global(3, node_y(self.node));
            set_global(1, get_global(1) + 1.0);
        }
    }
}
