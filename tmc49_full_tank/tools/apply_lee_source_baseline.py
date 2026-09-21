# -*- coding: utf-8 -*-
"""Apply the evidence-tracked TMC-49 baseline to runnable CFD configs.

Project snapshots are intentionally excluded: case_config.json is an immutable
record of the inputs used to produce an existing result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


LEE_SOURCE = "협력랩자료/26-1 조경제.pptx, PowerPoint 12번째 슬라이드(하단 표기 11쪽), TMC-49 Property 표"
TMC_TDS = (
    "문서/근거자료/TMC-49/TMC-49_TDS_Rev4_2026.pdf "
    "(TMC Industries 공식 Rev.4, 원 URL: "
    "https://tmcindustries.com/cdn/shop/files/TMC-49-TDS-Rev4.pdf?v=5304461421983960090)"
)
TMC_TDS_LEGACY = (
    "문서/근거자료/TMC-49/TMC-49_TDS_7.pdf "
    "(구판 49 degC 표기 이력, 원 URL: "
    "https://yottadeft.com/wp-content/uploads/2025/02/TMC-49_TDS_7.pdf)"
)
TMC_PRODUCT = "https://tmcindustries.com/products/tmc-49"
NIST_CP = "문서/근거자료/TMC-49/NIST_Heat_Capacity_of_Liquids_Supplement_I_2002.pdf, Table 21.51"
ALT_SAME_CAS = "https://www.fluorochemie.com/product/perfluoro4-methylpent-2-ene-tpd-hfpd"
FCM47_VAPOUR_GAP = "https://doi.org/10.1016/j.icheatmasstransfer.2026.111278"
FCM47_IOP = "https://doi.org/10.1088/1742-6596/2683/1/012030"
PFH_COOLPROP = "CoolProp 8.0.0 n-Perfluorohexane EOS, T=320.15 K saturated vapour"
PFH_TRANSPORT = "NIST IR 8209, DOI https://doi.org/10.6028/NIST.IR.8209, sec. 6.7.26"
AUDIT_DOC = "문서/CFD_Config_연구근거_및_설정기준_20260822.md"
IAPWS_LIQUID = "https://www.iapws.org/relguide/LiquidWater.html"

TMC_TABLES = {
    "rho": {
        "T_K": [253.15, 273.15, 293.15, 313.15, 333.15, 353.15, 373.15],
        "values": [1748.8, 1683.6, 1618.4, 1553.2, 1488.0, 1422.7, 1357.5],
        "unit": "kg/m3",
        "source": "TMC-49 TDS p.4, ASTM D4052",
        "evidence": "direct_manufacturer_table",
    },
    "cp": {
        "T_K": [253.15, 273.15, 293.15, 313.15, 333.15, 353.15, 373.15],
        "values": [705.0, 729.0, 754.0, 778.0, 802.0, 826.0, 850.0],
        "unit": "J/kg/K",
        "source": "TMC-49 TDS p.3, 표기 ASTM D7896",
        "evidence": "direct_manufacturer_table_with_conflict",
        "conflict": "NIST JPCRD 2002 Table 21.51 동일 CAS 회귀값은 293.1~313.1 K에서 약 550~584 J/kg/K이고, 별도 동일 CAS 공급사는 25 degC에서 1279 J/kg/K를 제시한다. 실제 사용 배치 CoA/DSC 확인 전에는 교수님 자료와 TMC 제품 TDS가 일치하는 제조사값을 사용.",
    },
    "mu": {
        "T_K": [289.15, 291.15, 294.15, 297.15, 300.15, 302.15, 305.15, 308.15, 313.15, 318.15],
        "values": [0.0006444188, 0.00062884404, 0.00060729264, 0.0005859564, 0.00056483532,
                   0.00055299288, 0.00053379664, 0.000514796, 0.0004845984, 0.0004564593],
        "unit": "Pa.s",
        "source": "TMC-49 TDS p.2 ASTM D445 kinematic viscosity multiplied by TDS p.4 interpolated density",
        "evidence": "derived_from_two_manufacturer_tables",
        "outside_range": "16~45 degC 밖은 가장 가까운 시험값으로 고정; 외삽하지 않음",
    },
    "kappa": {
        "T_K": [253.15, 273.15, 293.15, 313.15, 333.15, 353.15, 373.15],
        "values": [0.072, 0.069, 0.066, 0.063, 0.060, 0.057, 0.054],
        "unit": "W/m/K",
        "source": "TMC-49 TDS p.3, 표기 ASTM D7896",
        "evidence": "direct_manufacturer_table",
    },
}

SOURCE_VALUES = {
    "Tsat_C": 47.0,
    "h_fg_J_kg": 93220.0,
    "molWeight": 300.05,
    "sigma_lv": 0.01144,
    # TMC-49 직접값이 없어서 가장 가까운 공개 실험계인
    # perfluorohexane(C6F14)-물/증기 계면값을 유사물질 기준으로 사용한다.
    "sigma_lw": 0.0560,
    "sigma_vw": 0.0667,
    "property_tables": TMC_TABLES,
}

WATER_TABLES = {
    "T_K": [273.15, 283.15, 293.15, 303.15, 313.15, 323.15, 333.15, 343.15, 353.15, 363.15, 373.15],
    "rho": [999.84238, 999.70186, 998.20655, 995.64882, 992.21576, 988.03450,
            983.19525, 977.76401, 971.78979, 965.30901, 958.34838],
    "cp": [4219.318, 4195.142, 4184.189, 4179.899, 4179.356, 4181.226,
           4184.898, 4190.123, 4196.860, 4205.228, 4215.567],
    "mu": [0.0017917824, 0.0013059017, 0.0010015673, 0.0007972062, 0.0006527335,
           0.0005465265, 0.0004660393, 0.0004035454, 0.0003540461, 0.0003141733, 0.0002815811],
    "kappa": [0.55564768, 0.57878726, 0.59800465, 0.61437701, 0.62847972,
              0.64062961, 0.65101554, 0.65976703, 0.66698891, 0.67277785, 0.67722924],
}


def update_config(config: dict) -> bool:
    fluid = config.get("dielectric_fluid")
    if not isinstance(fluid, dict) or str(fluid.get("name", "")).strip().upper() != "TMC-49":
        return False

    config["_안내"] = (
        "시뮬레이션 단일 설정 소스. 2026-08-22 기준 TMC-49 제조사 온도별 시험표와 IAPWS DI수 표를 직접 사용한다. "
        "research_preliminary 상태이며 C6F14 유사 증기 수송물성·Lee 계수·유사물질 계면장력·정밀 형상은 후속 보정 대상이다."
    )
    config["_출처관리"] = {
        "기준": "직접 제조사 시험표 > 교수님 제공자료 > 동종 유체 문헌 > 보정 필요 모델 순으로 구분한다.",
        "TMC-49_교수님자료": LEE_SOURCE,
        "TMC-49_제조사자료": [TMC_TDS, TMC_PRODUCT],
        "TMC-49_구판충돌이력": TMC_TDS_LEGACY,
        "적용일": "2026-08-22",
        "상태구분": "direct / derived / analogous / calibration_required / unresolved를 구분한다.",
        "미확정값_목록": AUDIT_DOC,
    }
    config["_검증상태"] = {
        "등급": "research_preliminary",
        "정량검증완료": False,
        "사용범위": "물성 근거가 추적되는 연구용 기준 설정. 실험 보정 전 절대 기포율/응축거리의 확정 예측에는 사용하지 않는다.",
        "주요미확정": ["TMC-49 증기 직접 cp/mu/kappa", "Lee evap_C/cond_C", "TMC-49-물 직접 계면장력", "코일/CPU/프로브 정밀 형상", "상단 공기층/벽면 젖음성/비등 난류"],
    }
    config["_모델가정"] = {
        "headspace": {
            "evidence": "model_simplification",
            "value": "상단 공기 200 mm는 격자에서 생략하고 top을 prghTotalPressure 배출구로 처리",
            "reason": "현재 3상 비압축성 솔버에 공기상을 추가하지 않은 상태에서 증발 체적을 흡수하기 위한 수치 경계",
        },
        "turbulence": {
            "evidence": "calibration_required",
            "value": "laminar/Stokes",
            "reason": "직접 난류자료가 없어 기본 사용. 기포유도 난류 포함 여부는 실험과 민감도 검증 필요",
        },
        "heater_distribution": {
            "evidence": "derived",
            "value": "CPU 2개 footprint에 총 265 W를 면적비 균일 분배",
            "reason": "총 package power는 실측, 칩 내부 국소 발열지도는 미수령",
        },
        "coil_geometry": {
            "evidence": "calibration_required",
            "value": "상자형 경계+UA 대체모델",
            "reason": "실제 관경/핀/피치 CAD 미수령. 3 mm 기본 격자 실효 UA는 19.41 W/K",
        },
        "wall_wetting": {
            "evidence": "unresolved",
            "value": "접촉각/동적 젖음성 미보정",
            "reason": "TMC-49-고체 및 물-고체 직접 접촉각 자료 미수령",
        },
    }
    fluid.update(SOURCE_VALUES)
    for stale in ("poly_range_K", "rho_poly", "cp_poly", "mu_poly", "kappa_poly"):
        fluid.pop(stale, None)
    fluid["_설명"] = (
        "TMC-49(CAS 2070-70-4) 액체 물성. 제조사 TDS 온도별 시험표를 OpenFOAM tabulated 물성으로 직접 사용한다. "
        "표 내부는 선형보간하고 시험 범위 밖은 끝값으로 고정하며 임의 외삽하지 않는다."
    )
    fluid["CAS"] = "2070-70-4"
    fluid["_출처"] = [TMC_TDS, TMC_PRODUCT, LEE_SOURCE]
    fluid["_구판충돌이력"] = TMC_TDS_LEGACY
    fluid["_원자료_직접반영"] = (
        "비등점 47 degC; 분자량 300.05 g/mol; 잠열 93.22 kJ/kg; 25 degC 표면장력 11.44 mN/m; "
        "rho/cp/kinematic viscosity/kappa는 TDS 온도별 표. 동점도는 같은 TDS의 밀도와 곱해 동점성계수로 유도."
    )
    fluid["_물성제한"] = (
        "표 범위 밖 외삽은 하지 않는다. cp는 제조사/교수님 자료와 NIST 동일 CAS 실험 회귀값 사이에 차이가 있어 "
        "현재는 실제 사용 제품과 직접 연결되는 제조사값을 적용하고, 배치 CoA 또는 DSC 측정 전까지 불확실성으로 기록한다. "
        f"상충 근거: {NIST_CP}; 동일 CAS 별도 공급사 1.279 kJ/kg/K: {ALT_SAME_CAS}"
    )
    fluid["_h_fg"] = "원자료 93.22 kJ/kg을 SI 단위로 변환한 93220 J/kg."
    fluid["_sigma_lv"] = "원자료 11.44 mN/m를 SI 단위로 변환한 0.01144 N/m."
    fluid["_molWeight"] = "제조사 제품 페이지/TDS 직접값 300.05 g/mol. 제품 페이지 CAS 2070-70-4와 PubChem/NIST 분자량 300.04~300.045가 교차 확인됨."
    fluid["_sigma_삼각부등식"] = (
        "sigma_lv=0.01144 N/m는 TMC-49 제조사 직접값. sigma_lw=0.0560 N/m는 20~25 degC "
        "perfluorohexane(C6F14)-물 실험값, sigma_vw=0.0667 N/m는 20 degC 포화 perfluorohexane "
        "증기-물 실험값을 사용한 유사물질 대입값이다. TMC-49 직접값 수령 시 교체한다."
    )
    fluid["_sigma_lw_analog_source"] = "https://doi.org/10.1021/la00085a043; https://doi.org/10.1016/j.molliq.2020.113385"
    fluid["_sigma_vw_analog_source"] = "https://doi.org/10.1039/C3SM52289J"
    fluid["_sigma_evidence"] = {"sigma_lv": "direct", "sigma_lw": "analogous", "sigma_vw": "analogous"}
    fluid.pop("sigma_lv_협력원값", None)

    vapour = config.get("vapour")
    if isinstance(vapour, dict):
        vapour.update({"cp": 858.9821, "mu": 0.0000115262, "kappa": 0.0131966})
        vapour["_설명"] = (
            "TMC-49 증기 밀도는 제조사 분자량을 사용한 1 atm 이상기체 모델이다. 직접 증기 cp/mu/kappa는 공개 "
            "근거를 확보하지 못해 가장 가까운 공개 유사유체 n-perfluorohexane(C6F14)의 320.15 K 포화증기값을 "
            "사용한다. cp는 CoolProp 8.0 EOS, mu와 kappa는 NIST IR 8209의 희박기체 모델로 계산했다. 세 값 모두 "
            "analogous이며 TMC-49 직접 측정값이 아니다."
        )
        vapour["_evidence"] = {"density": "derived_ideal_gas", "cp": "analogous", "mu": "analogous", "kappa": "analogous"}
        vapour["_analog_source"] = [PFH_COOLPROP, PFH_TRANSPORT]
        vapour["_analog_calculation"] = (
            "n-C6F14 @ 320.15 K saturated vapour: cp=858.9821 J/kg/K; NIST Lennard-Jones epsilon/k=160 K, "
            "sigma=0.805 nm and Neufeld collision integral give mu=11.5262 microPa.s; NIST Eucken equations "
            "give kappa=0.0131966 W/m/K. TMC-49 direct values must replace these when available."
        )
        vapour["_source_gap"] = FCM47_VAPOUR_GAP
        vapour["_same_species_liquid_conflict"] = FCM47_IOP

    water = config.get("water")
    if isinstance(water, dict):
        water.update(WATER_TABLES)
        water["name"] = water.get("name") or "DI수"
        water["molWeight"] = 18.01528
        water["_설명"] = (
            "상단 DI수 물성. IAPWS SR6-08(2011)의 0.1 MPa 액체수 상관식으로 계산한 온도표를 "
            "OpenFOAM tabulated 물성으로 직접 사용한다. water는 기존 프로젝트 호환용 내부 상 이름이다."
        )
        water["_출처"] = [IAPWS_LIQUID, "IAPWS R6-95(2018), R12-08, R15-11"]
        water["_evidence"] = {"rho": "standard_correlation", "cp": "standard_correlation",
                              "mu": "standard_correlation", "kappa": "standard_correlation"}
        water["rho_30C"] = WATER_TABLES["rho"][3]
        water["cp_30C"] = WATER_TABLES["cp"][3]
        water["mu_30C"] = WATER_TABLES["mu"][3]
        water["kappa_30C"] = WATER_TABLES["kappa"][3]

    phase_change = config.get("phase_change")
    if isinstance(phase_change, dict):
        phase_change["_evidence"] = {"evap_C": "calibration_required", "cond_C": "calibration_required"}
        phase_change["_설명"] = (
            "Lee C [1/s]는 물성이 아니라 질량전달 완화 계수다. 현재 +/-50은 기존 수치 후보값이며 TMC-49 실험으로 "
            "검증되지 않았다. 교수님 T1~T6/기포율 시계열과 5/50/500 민감도로 보정하기 전 정량 확정값으로 쓰지 않는다."
        )
    return True


def write_config(path: Path, config: dict) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report files that need migration without writing")
    args = parser.parse_args()

    case_root = Path(__file__).resolve().parents[1]
    studio_configs = case_root.parent / "cfd_studio" / "configs"
    paths = [case_root / "config.json", *sorted(studio_configs.glob("*.json"))]
    changed = []
    for path in paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(config, ensure_ascii=False, sort_keys=True)
        if not update_config(config):
            continue
        after = json.dumps(config, ensure_ascii=False, sort_keys=True)
        if before == after:
            continue
        changed.append(path)
        if not args.check:
            write_config(path, config)

    action = "NEEDS_UPDATE" if args.check else "UPDATED"
    for path in changed:
        print(f"{action} {path}")
    print(f"{action}_COUNT={len(changed)}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
