"""Small perspective renderer for the mouse preview."""
import math

from gi.repository import Gtk


class MouseView(Gtk.DrawingArea):
    # Longitudinal sections from the front buttons to the heel.
    SECTIONS = [
        (-1.22, .03, .08), (-1.16, .40, .14), (-1.00, .55, .22),
        (-.72, .57, .33), (-.40, .53, .42), (-.10, .50, .49),
        (.20, .54, .54), (.48, .59, .54), (.74, .56, .48),
        (.95, .45, .34), (1.09, .28, .18), (1.12, .04, .08),
    ]
    RIBS = 14

    def __init__(self):
        super().__init__(content_width=360, content_height=300, hexpand=True, vexpand=True)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Rotatable mouse preview"])
        self.yaw, self.pitch = -.47, .79
        self.rgb, self.brightness = (.95, .20, .30), .72
        self.set_draw_func(self.draw)
        drag = Gtk.GestureDrag(button=1)
        drag.connect("drag-begin", self.begin_drag)
        drag.connect("drag-update", self.drag)
        self.add_controller(drag)

    def begin_drag(self, *_args):
        self.start = self.yaw, self.pitch

    def drag(self, _gesture, x, y):
        self.yaw = self.start[0] + x * .012
        self.pitch = max(.16, min(1.52, self.start[1] + y * .009))
        self.queue_draw()

    @classmethod
    def cross_section(cls, width, height, index, y):
        angle = math.pi * index / cls.RIBS
        return -width * math.cos(angle), y, .04 + height * math.sin(angle) ** .8

    def mesh(self):
        for lo, hi in zip(self.SECTIONS, self.SECTIONS[1:]):
            y1, w1, h1 = lo
            y2, w2, h2 = hi
            for index in range(self.RIBS):
                vertices = [
                    self.cross_section(w1, h1, index, y1),
                    self.cross_section(w1, h1, index + 1, y1),
                    self.cross_section(w2, h2, index + 1, y2),
                    self.cross_section(w2, h2, index, y2),
                ]
                light = .42 + .49 * math.sin(math.pi * (index + .5) / self.RIBS)
                shade = .082 + .19 * light
                if y2 <= -.40 and index >= self.RIBS // 2:
                    shade *= .88
                yield vertices, (shade, shade * 1.03, shade * 1.12)

    def draw(self, _area, cr, width, height):
        zoom = min(width, height) * .34
        sin_y, cos_y = math.sin(self.yaw), math.cos(self.yaw)
        sin_p, cos_p = math.sin(self.pitch), math.cos(self.pitch)

        def project(vertex):
            x, y, z = vertex
            dx, dy = x * cos_y - y * sin_y, x * sin_y + y * cos_y
            depth = dy * cos_p + z * sin_p
            perspective = zoom * 4.9 / (4.9 - depth)
            return width / 2 + dx * perspective, height / 2 + (
                dy * sin_p - z * cos_p) * perspective + 14, depth

        def path(points, close=False):
            cr.move_to(*points[0][:2])
            for point in points[1:]:
                cr.line_to(*point[:2])
            if close:
                cr.close_path()

        # Render far faces first. The raised wheel and button follow the same projection.
        faces = []
        for vertices, color in self.mesh():
            points = list(map(project, vertices))
            faces.append((sum(p[2] for p in points), points, color))
        for _, points, color in sorted(faces, key=lambda face: face[0]):
            path(points, True)
            cr.set_source_rgb(*color)
            cr.fill_preserve()
            cr.set_line_width(.7)
            cr.stroke()
        seams = [
            [(0, -1.18, .14), (0, -1, .265), (0, -.72, .375), (0, -.4, .465)],
            [(-.53, -.4, .045), (-.32, -.40, .40), (0, -.40, .466),
             (.32, -.40, .40), (.53, -.40, .045)],
        ]
        cr.set_line_width(1.6)
        cr.set_source_rgba(.04, .045, .05, .94)
        for seam in seams:
            path(list(map(project, seam)))
            cr.stroke()
        dpi = [(-.058, -.29, .49), (.058, -.29, .49),
               (.058, -.20, .51), (-.058, -.20, .51)]
        path(list(map(project, dpi)), True)
        cr.set_source_rgb(.065, .069, .080)
        cr.fill()
        wheel = [(-.083, -.78, .372), (-.083, -.70, .44), (-.083, -.59, .464),
                 (-.083, -.48, .421), (.083, -.48, .421), (.083, -.59, .464),
                 (.083, -.70, .44), (.083, -.78, .372)]
        path(list(map(project, wheel)), True)
        cr.set_source_rgb(.055, .06, .07)
        cr.fill()
        path(list(map(project, [(0, -.76, .402), (0, -.67, .453),
                                (0, -.59, .469), (0, -.50, .435)])))
        cr.set_line_width(4.5)
        cr.set_line_cap(1)
        cr.set_source_rgb(*(channel * (.12 + .88 * self.brightness) for channel in self.rgb))
        cr.stroke()
