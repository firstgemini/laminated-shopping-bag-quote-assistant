import unittest

from quote_app.calculations import (
    HANDLE_BODY,
    QuoteInputs,
    QuoteValidationError,
    calculate_freight,
    calculate_quote,
    carton_height_cm,
    quantity_loss_cny,
    quantity_profit_cny,
)


MATERIAL = "无纺布覆膜二等材料"


def sample_inputs(**changes) -> QuoteInputs:
    values = {
        "width_cm": 40.0,
        "height_cm": 35.0,
        "gusset_cm": 12.0,
        "handle_length_cm": 70.0,
        "quantity": 10_000,
        "exchange_rate": 6.7,
        "material": MATERIAL,
        "gsm_label": "150克",
        "handle_type": HANDLE_BODY,
        "handle_width_cm": 2.5,
    }
    values.update(changes)
    return QuoteInputs(**values)


class QuantityTierTests(unittest.TestCase):
    def test_loss_boundaries(self):
        self.assertEqual(quantity_loss_cny(2_000), 0.30)
        self.assertEqual(quantity_loss_cny(2_100), 0.25)
        self.assertEqual(quantity_loss_cny(3_000), 0.25)
        self.assertEqual(quantity_loss_cny(5_000), 0.20)
        self.assertEqual(quantity_loss_cny(9_900), 0.15)
        self.assertEqual(quantity_loss_cny(10_000), 0.10)

    def test_profit_boundaries(self):
        self.assertEqual(quantity_profit_cny(1_000), 0.40)
        self.assertEqual(quantity_profit_cny(1_100), 0.35)
        self.assertEqual(quantity_profit_cny(2_000), 0.35)
        self.assertEqual(quantity_profit_cny(3_000), 0.30)
        self.assertEqual(quantity_profit_cny(5_000), 0.25)
        self.assertEqual(quantity_profit_cny(25_000), 0.20)
        self.assertEqual(quantity_profit_cny(50_000), 0.15)
        self.assertEqual(quantity_profit_cny(50_100), 0.10)

    def test_quantity_must_be_whole_cartons(self):
        with self.assertRaisesRegex(QuoteValidationError, "100的整数倍"):
            calculate_quote(
                sample_inputs(quantity=1_050),
                material_price_cny_per_m2=1.67,
                material_gsm=150,
            )


class CartonHeightTests(unittest.TestCase):
    def test_height_boundaries_are_locked(self):
        self.assertEqual(carton_height_cm(MATERIAL, 29.5), 32)
        self.assertEqual(carton_height_cm(MATERIAL, 30), 30)
        self.assertEqual(carton_height_cm(MATERIAL, 38), 30)
        self.assertEqual(carton_height_cm(MATERIAL, 38.5), 27)


class FreightTests(unittest.TestCase):
    def test_single_shipment_boundaries(self):
        self.assertEqual(calculate_freight(14.999).mode, "LCL拼箱")
        self.assertEqual(calculate_freight(15).mode, "20GP")
        self.assertEqual(calculate_freight(28).mode, "20GP")
        self.assertEqual(calculate_freight(28.001).mode, "40HQ")
        self.assertEqual(calculate_freight(68).mode, "40HQ")
        self.assertEqual(calculate_freight(68.001).mode, "45HQ")
        self.assertEqual(calculate_freight(78).mode, "45HQ")

    def test_multi_container_split(self):
        result = calculate_freight(80)
        self.assertEqual(result.mode, "40HQ + LCL拼箱")
        self.assertEqual(result.components[0].count, 1)
        self.assertAlmostEqual(result.components[1].cbm, 12)
        self.assertAlmostEqual(result.total_cost_cny, 9_000 + 1_390 + 12 * 75)

        exact = calculate_freight(136)
        self.assertEqual(exact.mode, "2×40HQ")
        self.assertEqual(len(exact.components), 1)
        self.assertEqual(exact.total_cost_cny, 18_000)


class QuoteCalculationTests(unittest.TestCase):
    def test_reference_body_handle_quote(self):
        result = calculate_quote(
            sample_inputs(),
            material_price_cny_per_m2=1.67,
            material_gsm=150,
        )
        self.assertEqual(result.carton_count, 100)
        self.assertAlmostEqual(result.layout_width_cm, 54)
        self.assertAlmostEqual(result.layout_height_cm, 87)
        self.assertAlmostEqual(result.fabric_area_m2, 0.4698)
        self.assertAlmostEqual(result.total_cbm, 5.031)
        self.assertEqual(result.freight.mode, "LCL拼箱")
        self.assertAlmostEqual(
            result.exw_cny,
            result.body_cost_cny
            + result.binding_cost_cny
            + result.handle_cost_cny
            + 0.50
            + 0.05
            + result.carton_share_cny
            + result.loss_cny
            + result.profit_cny,
        )
        self.assertAlmostEqual(
            result.fob_cny,
            result.exw_cny + result.freight.total_cost_cny / 10_000,
        )


if __name__ == "__main__":
    unittest.main()
