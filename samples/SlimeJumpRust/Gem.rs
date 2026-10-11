// A gem: picked up when the slime comes close (and counted in the globals). It stays picked up once the slime has reached a checkpoint after it;
// if the slime dies first, it is back where it was.
use stride2d::*;

#[script(max_instances = 32)]
struct Gem {
    node: i32,
    state: i32,         // 0 there, 1 picked up (not kept yet), 2 kept
    saves: i32,
    deaths: i32,
    home_y: f32,
}

impl Gem {
    fn start(&mut self) {
        self.saves = get_global(1) as i32;
        self.deaths = get_global(0) as i32;
        self.home_y = node_y(self.node);
    }

    fn fixed_update(&mut self) {
        let saves: i32 = get_global(1) as i32;
        let deaths: i32 = get_global(0) as i32;
        if saves != self.saves {
            self.saves = saves;
            if self.state == 1 { self.state = 2; }
        }
        if deaths != self.deaths {
            self.deaths = deaths;
            if self.state == 1 {
                self.state = 0;
                set_pos(self.node, node_x(self.node), self.home_y);
                set_global(4, get_global(4) - 1.0);
            }
        }
        if self.state != 0 { return; }
        let s: i32 = (get_global(21) as i32) - 1;
        if s < 0 { return; }
        let dx: f32 = node_x(s) - node_x(self.node);
        let dy: f32 = node_y(s) - node_y(self.node);
        if dx > -0.7 && dx < 0.7 && dy > -0.7 && dy < 0.7 {
            self.state = 1;
            set_pos(self.node, node_x(self.node), self.home_y - 100.0);       // (far below the level: not seen. A node that is switched off would not run to come back.)
            set_global(4, get_global(4) + 1.0);
        }
    }
}
