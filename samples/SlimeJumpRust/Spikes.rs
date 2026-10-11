// Spikes: the slime is hurt when it touches them (tag 9 is how the bot knows where they are).
use stride2d::*;

#[script(max_instances = 32)]
struct Spikes {
    node: i32,
}

impl Spikes {
    fn start(&mut self) {
        set_tag(self.node, 9);
    }

    fn fixed_update(&mut self) {
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - node_x(self.node);
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -0.6 && dx < 0.6 && dy > -0.55 && dy < 0.55 { set_tag(s, 3); }
    }
}
