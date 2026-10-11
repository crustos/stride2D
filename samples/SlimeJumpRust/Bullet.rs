// A bullet from the blaster: flies straight (the Slime script puts it at the slime, turns it toward the aim point and gives it this script), is gone when it meets a wall
// or after a second and a bit, and shoots a worm (tag 2) it comes to: the worm's tag becomes 5 and the worm takes it from there.
use stride2d::*;

const BULLET_SPEED: f32 = 30.0;
const DT: f32 = 0.016666668;

#[script(max_instances = 8)]
struct Bullet {
    node: i32,
    dx: f32,
    dy: f32,
    life: f32,
}

impl Bullet {
    fn start(&mut self) {
        let a: f32 = node_angle(self.node);
        self.dx = math_cos(a);
        self.dy = math_sin(a);
        self.life = 1.2;
        add_sprite(self.node, 1, 0.3, 0.3, 1.0, 0.9, 0.3);
    }

    fn fixed_update(&mut self) {
        self.life -= DT;
        let step: f32 = BULLET_SPEED * DT;
        let x: f32 = node_x(self.node);
        let y: f32 = node_y(self.node);
        if self.life <= 0.0 || raycast(x, y, self.dx, self.dy, step + 0.2, 1) >= 0 {
            destroy_node(self.node);
            return;
        }
        let nx: f32 = x + self.dx * step;
        let ny: f32 = y + self.dy * step;
        set_pos(self.node, nx, ny);
        let mut i: i32 = 0;
        let n: i32 = node_slots();
        while i < n {
            if get_tag(i) == 2 {
                let ex: f32 = node_x(i) - nx;
                let ey: f32 = node_y(i) - ny;
                if ex > -0.6 && ex < 0.6 && ey > -0.6 && ey < 0.6 {
                    set_tag(i, 5);
                    destroy_node(self.node);
                    return;
                }
            }
            i += 1;
        }
    }
}
