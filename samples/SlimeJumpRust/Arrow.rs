// An arrow from a turret: flies straight, hurts the slime it hits (its tag becomes 3), is gone against a wall or after four seconds. Its tag is 4 (the bot looks for it).
use stride2d::*;

const ARROW_SPEED: f32 = 9.0;
const DT: f32 = 0.016666668;

#[script(max_instances = 8)]
struct Arrow {
    node: i32,
    dx: f32,
    dy: f32,
    life: f32,
}

impl Arrow {
    fn start(&mut self) {
        let a: f32 = node_angle(self.node);
        self.dx = math_cos(a);
        self.dy = math_sin(a);
        self.life = 4.0;
        set_tag(self.node, 4);
        add_sprite(self.node, 0, 0.7, 0.12, 0.9, 0.8, 0.5);
    }

    fn fixed_update(&mut self) {
        self.life -= DT;
        let step: f32 = ARROW_SPEED * DT;
        let x: f32 = node_x(self.node);
        let y: f32 = node_y(self.node);
        if self.life <= 0.0 || raycast(x, y, self.dx, self.dy, step + 0.35, 1) >= 0 {
            destroy_node(self.node);
            return;
        }
        let nx: f32 = x + self.dx * step;
        let ny: f32 = y + self.dy * step;
        set_pos(self.node, nx, ny);
        let s: i32 = (get_global(21) as i32) - 1;
        if s >= 0 {
            let ex: f32 = node_x(s) - nx;
            let ey: f32 = node_y(s) - ny;
            if ex > -0.55 && ex < 0.55 && ey > -0.8 && ey < 0.8 {
                set_tag(s, 3);
                destroy_node(self.node);
            }
        }
    }
}
