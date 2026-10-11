// A crumbly platform: solid, but a second after the slime has stood on it, it dissolves (until the slime is back at its checkpoint).
use stride2d::*;

const DT: f32 = 0.016666668;

#[script(max_instances = 16)]
struct Crumbly {
    node: i32,
    timer: f32,
    gone: i32,
    deaths: i32,
    home_x: f32,
    home_y: f32,
}

impl Crumbly {
    fn start(&mut self) {
        add_body(self.node, 0);
        add_box(self.node, 1.0, 1.0);
        self.deaths = get_global(0) as i32;
        self.home_x = node_x(self.node);
        self.home_y = node_y(self.node);
    }

    fn fixed_update(&mut self) {
        let d: i32 = get_global(0) as i32;
        if d != self.deaths {                       // the slime died: the platform is back
            self.deaths = d;
            self.timer = 0.0;
            if self.gone != 0 {
                self.gone = 0;
                set_pos(self.node, self.home_x, self.home_y);
            }
        }
        if self.gone != 0 { return; }
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - node_x(self.node);
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -0.95 && dx < 0.95 && dy > 0.7 && dy < 1.1 { self.timer += DT; }
        if self.timer >= 1.0 {
            self.gone = 1;
            set_pos(self.node, self.home_x, self.home_y - 100.0);       // (far below the level: not solid, not seen. A node that is switched off would not run to come back.)
        }
    }
}
