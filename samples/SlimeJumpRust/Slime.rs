// The player, ported from SlimeJump's Player.cs and Lasso.cs: walk, a jump you can cut short, climbing the vines, a blaster, a lasso to swing on,
// back to the last checkpoint when hurt or fallen. (Input is the keyboard and mouse, or the Bot's numbers in the globals when it is switched on.)
//
// Rust, the Crust subset: the engine's calls are set_pos, set_velocity, raycast, overlap_box ... (src/engine/Engine.cs, in snake_case), nodes are i32 handles, and the scripts
// talk through node tags (1 slime, 2 worm, 3 "the slime was hurt", 4 arrow, 6 bullet) and the globals below.
use stride2d::*;

const G_DEATHS: i32 = 0;
const G_SAVES: i32 = 1;
const G_SAVE_X: i32 = 2;
const G_SAVE_Y: i32 = 3;
const G_BOT: i32 = 6;          // 1: the bot plays (the numbers below come from it)
const G_IN_MOVE: i32 = 7;
const G_IN_JUMP: i32 = 8;
const G_IN_ATTACK: i32 = 9;
const G_AIM_X: i32 = 10;
const G_AIM_Y: i32 = 11;
const G_IN_LASSO: i32 = 12;
const G_IN_REEL: i32 = 13;
const G_GROUNDED: i32 = 15;    // what the bot looks at
const G_CLIMBING: i32 = 16;
const G_JUMPING: i32 = 17;
const G_ATTACHED: i32 = 18;
const G_PLAYER: i32 = 21;      // the slime's node + 1

const MASK_WALL: i32 = 1;          // layer 0: the walls (what the probes and the rope meet)
const MOVE_SPEED: f32 = 7.0;
const JUMP_SPEED: f32 = 12.5;
const CLIMB_SPEED: f32 = 7.0;
const CLIMB_FALL: f32 = 2.0;
const DT: f32 = 0.016666668;
const LASSO_MAX: f32 = 7.0;
const LASSO_SPEED: f32 = 20.0;
const SWING_ACCEL: f32 = 28.0;
const SWING_MAX: f32 = 11.0;

#[script(max_instances = 1)]
struct Slime {
    node: i32,
    rope: i32,
    jumping: i32,
    climbing: i32,
    lock: f32,          // seconds left of a respawn pause
    shoot_timer: f32,
    lasso: i32,         // 0 not out, 1 flying, 2 attached
    prev_lasso: i32,
    off_x: f32,         // the flying tip, from the slime
    off_y: f32,
    dir_x: f32,
    dir_y: f32,
    tip_x: f32,
    tip_y: f32,
    len: f32,
}

fn bot() -> i32 {
    if get_global(G_BOT) > 0.5 { return 1; }
    return 0;
}

fn in_move() -> f32 {
    if bot() != 0 { return get_global(G_IN_MOVE); }
    let mut dir: f32 = 0.0;
    if key_down(263) != 0 || key_down(65) != 0 { dir -= 1.0; }     // left arrow, A
    if key_down(262) != 0 || key_down(68) != 0 { dir += 1.0; }     // right arrow, D
    return dir;
}

fn in_jump() -> i32 {
    if bot() != 0 { if get_global(G_IN_JUMP) > 0.5 { return 1; } return 0; }
    if key_down(32) != 0 || key_down(265) != 0 || key_down(87) != 0 { return 1; }     // space, up arrow, W
    return 0;
}

fn in_attack() -> i32 {
    if bot() != 0 { if get_global(G_IN_ATTACK) > 0.5 { return 1; } return 0; }
    return mouse_down(0);
}

fn in_lasso() -> i32 {
    if bot() != 0 { if get_global(G_IN_LASSO) > 0.5 { return 1; } return 0; }
    return mouse_down(2);
}

fn in_reel() -> f32 {
    if bot() != 0 { return get_global(G_IN_REEL); }
    let mut r: f32 = 0.0;
    if key_down(87) != 0 || key_down(265) != 0 { r -= 1.0; }      // W reels in
    if key_down(83) != 0 || key_down(264) != 0 { r += 1.0; }      // S lets out
    return r;
}

fn aim_x() -> f32 {
    if bot() != 0 { return get_global(G_AIM_X); }
    return mouse_world_x();
}

fn aim_y() -> f32 {
    if bot() != 0 { return get_global(G_AIM_Y); }
    return mouse_world_y();
}

fn dist(dx: f32, dy: f32) -> f32 {
    return math_sqrt(dx * dx + dy * dy);
}

impl Slime {
    fn start(&mut self) {
        let x: f32 = node_x(self.node);
        let y: f32 = node_y(self.node);
        if get_global(G_SAVES) < 0.5 {
            set_global(G_SAVE_X, x);
            set_global(G_SAVE_Y, y);
        }
        set_layer(self.node, 6);
        add_body_ex(self.node, 2, 1, 1.0);        // dynamic, does not tumble
        add_box_ex(self.node, 0.9, 0.75, 0.0);    // no friction: it slides down a wall instead of sticking to it
        set_tag(self.node, 1);
        set_global(G_PLAYER, self.node as f32 + 1.0);
        self.rope = new_node();
        add_sprite(self.rope, 0, 1.0, 0.07, 0.85, 0.65, 0.3);
        set_active(self.rope, 0);
    }

    fn fixed_update(&mut self) {
        let x: f32 = node_x(self.node);
        let y: f32 = node_y(self.node);
        if self.lock > 0.0 {
            self.lock -= DT;
            set_velocity(self.node, 0.0, 0.0);
            return;
        }
        if get_tag(self.node) == 3 || y < -3.0 {
            self.die();
            return;
        }
        let half_w: f32 = 0.45;
        let half_h: f32 = 0.375;

        self.update_lasso(x, y);
        let attached: i32 = if self.lasso == 2 { 1 } else { 0 };

        // the blaster, toward the aim point
        self.shoot_timer -= DT;
        if in_attack() != 0 && self.shoot_timer <= 0.0 {
            let mut ax: f32 = aim_x() - x;
            let mut ay: f32 = aim_y() - y;
            let al: f32 = dist(ax, ay);
            if al < 0.001 { ax = 1.0; ay = 0.0; }
            self.shoot_timer = 0.35;
            let b: i32 = new_node();
            if b >= 0 {
                set_pos(b, x, y);
                set_angle(b, math_atan2(ay, ax));
                set_tag(b, 6);
                attach_script(b, SCRIPT_BULLET);
            }
        }

        let mut vy: f32 = velocity_y(self.node);
        let mut vx: f32 = velocity_x(self.node);
        let m: f32 = in_move();
        let jump: i32 = in_jump();
        let grounded: i32 = if overlap_box(x, y - half_h - 0.05, half_w * 0.9, 0.06, MASK_WALL) > 0 { 1 } else { 0 };    // something solid just under its feet

        // walking: a wall in the way stops it (so it can slide down it)
        let mut hitting_wall: i32 = 0;
        if m != 0.0 {
            let side: f32 = if m > 0.0 { 1.0 } else { -1.0 };
            if overlap_box(x + side * (half_w + 0.03), y, 0.03, half_h * 0.9, MASK_WALL) > 0 { hitting_wall = 1; }
        }
        if attached == 0 {
            if hitting_wall == 0 && grounded != 0 && m != 0.0 && vx > -0.5 && vx < 0.5 && self.lock <= 0.0 {
                set_pos(self.node, x, y + 0.03);                // stopped by nothing it can see: the seam between two blocks catching its corner; a hop over it
            }
            vx = 0.0;
            if hitting_wall == 0 { vx = m * MOVE_SPEED; }
        }

        // climbing: touching a vine; jump climbs, otherwise slide down slowly
        let was_climbing: i32 = self.climbing;
        self.climbing = 0;
        if attached == 0 && overlap_box(x, y, 0.6, 0.225, 32768) > 0 { self.climbing = 1; }

        // jumping (let go early for a short hop)
        if self.climbing == 0 && attached == 0 {
            if jump != 0 && grounded != 0 && self.jumping == 0 {
                vy = JUMP_SPEED;
                self.jumping = 1;
            } else if self.jumping != 0 {
                if jump == 0 {
                    if vy > 0.0 { vy = vy * 0.4; }
                    self.jumping = 0;
                } else if vy <= 0.0 {
                    self.jumping = 0;
                }
            }
        }
        if self.climbing != 0 {
            if jump != 0 { vy = CLIMB_SPEED; self.jumping = 1; } else { vy = -CLIMB_FALL; self.jumping = 0; }
        } else if was_climbing != 0 && jump != 0 {
            vy = JUMP_SPEED * 0.8;                 // pop over the lip
        }
        if attached == 0 { set_velocity(self.node, vx, vy); }

        set_global(G_GROUNDED, grounded as f32);
        set_global(G_CLIMBING, self.climbing as f32);
        set_global(G_JUMPING, self.jumping as f32);
        set_global(G_ATTACHED, attached as f32);
    }

    // The lasso: the right mouse button throws a hook toward the pointer; it flies until it meets a wall, then the slime swings on the rope
    // (W / S reel it in and out, A / D pump the swing); letting go of the button lets go of the rope and keeps the swing's speed.
    fn update_lasso(&mut self, x: f32, y: f32) {
        let input: i32 = in_lasso();
        if input != 0 && self.prev_lasso == 0 {
            let mut ax: f32 = aim_x() - x;
            let mut ay: f32 = aim_y() - y;
            let al: f32 = dist(ax, ay);
            if al < 0.001 { ax = 0.0; ay = 1.0; }
            let n: f32 = dist(ax, ay);
            self.dir_x = ax / n;
            self.dir_y = ay / n;
            self.off_x = 0.0;
            self.off_y = 0.0;
            self.lasso = 1;
        } else if input == 0 && self.prev_lasso != 0 {
            self.lasso = 0;
        }
        self.prev_lasso = input;
        if self.lasso == 1 {
            let reach: f32 = dist(self.off_x, self.off_y);
            let mut step: f32 = LASSO_SPEED * DT;
            if LASSO_MAX - reach < step { step = LASSO_MAX - reach; }
            let hit: i32 = if step > 0.0 { raycast(x + self.off_x, y + self.off_y, self.dir_x, self.dir_y, step, MASK_WALL) } else { -1 };
            if hit >= 0 {
                self.tip_x = ray_x();
                self.tip_y = ray_y();
                self.len = dist(self.tip_x - x, self.tip_y - y);
                self.lasso = 2;
            } else if step <= 0.0 {
                self.lasso = 0;
            } else {
                self.off_x += self.dir_x * step;
                self.off_y += self.dir_y * step;
                self.tip_x = x + self.off_x;
                self.tip_y = y + self.off_y;
            }
        }
        if self.lasso == 2 {
            let reel: f32 = in_reel();
            self.len += reel * 7.0 * DT;
            if self.len < 0.5 { self.len = 0.5; }
            if self.len > LASSO_MAX { self.len = LASSO_MAX; }
            let mut dx: f32 = x - self.tip_x;
            let mut dy: f32 = y - self.tip_y;
            let d: f32 = dist(dx, dy);
            let mut vx: f32 = velocity_x(self.node);
            let mut vy: f32 = velocity_y(self.node);
            if d > 0.001 {
                let nx: f32 = dx / d;
                let ny: f32 = dy / d;
                if d >= self.len - 0.02 {                          // taut: no speed away from the hook, and a pull back onto the circle if it has drifted out
                    let vn: f32 = vx * nx + vy * ny;
                    if vn > 0.0 { vx -= nx * vn; vy -= ny * vn; }
                    if d > self.len {
                        vx -= nx * (d - self.len) * 12.0;
                        vy -= ny * (d - self.len) * 12.0;
                    }
                }
                let m: f32 = in_move();
                if m != 0.0 {                                      // pump the swing along the circle, toward where the player pushes
                    let mut tx: f32 = -ny;
                    let mut ty: f32 = nx;
                    if tx * m < 0.0 { tx = -tx; ty = -ty; }
                    if vx * tx + vy * ty < SWING_MAX {                  // (up to a top speed)
                        vx += tx * SWING_ACCEL * DT;
                        vy += ty * SWING_ACCEL * DT;
                    }
                }
                set_velocity(self.node, vx, vy);
            }
        }
        if self.lasso != 0 {
            let sx: f32 = self.tip_x - x;
            let sy: f32 = self.tip_y - y;
            set_active(self.rope, 1);
            set_pos(self.rope, x + sx * 0.5, y + sy * 0.5);
            set_angle(self.rope, math_atan2(sy, sx));
            set_scale(self.rope, dist(sx, sy), 1.0);
        } else {
            set_active(self.rope, 0);
        }
    }

    fn die(&mut self) {
        set_global(G_DEATHS, get_global(G_DEATHS) + 1.0);
        set_pos(self.node, get_global(G_SAVE_X), get_global(G_SAVE_Y));
        set_velocity(self.node, 0.0, 0.0);
        set_tag(self.node, 1);
        self.jumping = 0;
        self.climbing = 0;
        self.lasso = 0;
        set_active(self.rope, 0);
        self.lock = 0.5;
    }
}
