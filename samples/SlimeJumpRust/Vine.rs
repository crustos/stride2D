// Vines: a trigger on layer 15, which the slime's probe finds (it climbs while it overlaps one).
use stride2d::*;

#[script(max_instances = 32)]
struct Vine {
    node: i32,
}

impl Vine {
    fn start(&mut self) {
        set_layer(self.node, 15);
        add_body(self.node, 0);
        add_box_trigger(self.node, 1.0, 1.0);
    }
}
