// An anchor: a solid block the lasso can catch on (tag 7, which is how the bot finds it).
use stride2d::*;

#[script(max_instances = 8)]
struct Anchor {
    node: i32,
}

impl Anchor {
    fn start(&mut self) {
        add_body(self.node, 0);
        add_box(self.node, 1.0, 1.0);
        set_tag(self.node, 7);
    }
}
