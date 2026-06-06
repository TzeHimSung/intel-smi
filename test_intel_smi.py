import unittest
from unittest.mock import patch

import intel_smi


class ProcessRenderingTests(unittest.TestCase):
    def test_process_memory_is_rendered_with_readable_unit(self):
        rows = [
            {
                "device_id": 0,
                "process_id": 44967,
                "process_name": "stable-diffusion-v1-5-int8-ov",
                "mem_size": "4037068",
            }
        ]

        with patch("intel_smi.process_rows", return_value=rows):
            output = "\n".join(intel_smi.render_processes())

        self.assertIn("3.85GiB", output)
        self.assertNotIn("4037068", output)


if __name__ == "__main__":
    unittest.main()
