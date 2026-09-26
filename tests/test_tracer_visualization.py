"""Regression tests for cell order, fixed color scale and physical plot aspect."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

AVAILABLE=bool(importlib.util.find_spec('numpy') and importlib.util.find_spec('matplotlib'))
if AVAILABLE:
    import numpy as np
    from tracer_transport.plot_case import concentration_figure,plt


@unittest.skipUnless(AVAILABLE,'Install tracer requirements for visualization tests')
class VisualizationTests(unittest.TestCase):
    def fixture(self,root,invalid_q=False):
        c=np.arange(3*2*2*4,dtype=float).reshape(3,2,2,4)
        q=c/10
        if invalid_q:
            q[1,0,0,0]=np.nan
        np.savez(root/'concentration.npz',times=[0,.5,1],concentration=c.reshape(3,-1),
                 sorbed_bulk=q.reshape(3,-1),shape_xyz=[4,2,2],lengths_m=[2,.6,.4],
                 region_id=np.ones(16,dtype=int))
        (root/'config.json').write_text(json.dumps({'shape_xyz':[4,2,2],'lengths_m':[2,.6,.4],
            'kind':'porous','porous_boxes_m':[{'min':[0,0,0],'max':[2,.6,.4]}]}))
        return c,q

    def test_exact_slice_orientation_scale_and_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c,q=self.fixture(root)
            fig,axes=concentration_figure(root)
            try:
                for row,field in enumerate([c,q]):
                    limits=[]
                    for col in range(3):
                        image=axes[row,col].images[0]
                        np.testing.assert_array_equal(image.get_array(),field[col,:,1,:])
                        self.assertEqual(image.origin,'lower')
                        self.assertEqual(image.get_interpolation(),'nearest')
                        self.assertEqual(axes[row,col].get_aspect(),1.)
                        self.assertEqual(list(image.get_extent()),[0,2,0,.4])
                        limits.append((image.norm.vmin,image.norm.vmax))
                    self.assertEqual(len(set(limits)),1)
                fig.canvas.draw()
                renderer=fig.canvas.get_renderer()
                title_box=fig._suptitle.get_window_extent(renderer)
                self.assertGreaterEqual(title_box.y0,0)
                self.assertLessEqual(title_box.y1,fig.bbox.height)
                for ax in fig.axes:
                    for label in [ax.xaxis.label,ax.yaxis.label,ax.title]:
                        if label.get_text():
                            box=label.get_window_extent(renderer)
                            self.assertGreaterEqual(box.x0,-1)
                            self.assertGreaterEqual(box.y0,-1)
                            self.assertLessEqual(box.x1,fig.bbox.width+1)
                            self.assertLessEqual(box.y1,fig.bbox.height+1)
            finally:
                plt.close(fig)

    def test_invalid_sorbed_data_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,True)
            with self.assertRaises(ValueError):
                concentration_figure(root)


if __name__=='__main__':
    unittest.main()
