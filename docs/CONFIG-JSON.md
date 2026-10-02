# Config JSON

## 작성 순서

1. 설문과 솔버 선택으로 CFD Template 생성
2. **양식 편집 → JSON 내보내기**로 생성된 양식 확보
3. 해당 양식의 항목·단위·형상 식별자를 기준으로 Config 값 입력
4. 필요한 추가 항목만 스키마에 명시하여 확장
5. **JSON 가져오기** 또는 **전체 JSON → JSON 저장**으로 초안 반영
6. 입력 목록과 3D 미리보기에서 사용자 확인 후 최종 저장

- 값 입력과 양식 정의는 분리 · 미확정 물성이나 경계조건을 임의로 채우지 않음
- 계산 적용은 솔버별 실행 연결 범위에 따름 · JSON에 추가된 항목이 자동으로 솔버 기능이 되지는 않음

## 파일 형식

| 형식 | 내용 | 용도 |
| --- | --- | --- |
| Template | `version: 1`, `fields` | 입력 양식과 초기 형상 |
| Config 내보내기 | `format: "cfd-studio-config"`, `version: 1`, `config`, `config_schema` | 입력값과 표시 양식 함께 보존 |
| 기존 Config 객체 | 실제 키와 값 | 기존 파일 호환 · 기존 Template 정의와 자료형을 기준으로 표시 |
| 공간 문서 | 공간 JSON 창에서 출력된 형식 | 전체 형상·공간 관계 편집 |

- Config 내보내기 파일에서 실제 계산 입력 객체는 `config`
- 전체 JSON 편집창은 현재 범위의 값 객체를 표시 · 양식과 값을 함께 변경할 때는 내보낸 Config 문서 사용
- `config_schema`는 Studio의 버전 1 필드 정의 · 범용 JSON Schema 전체 규격은 아님
- 공간 JSON과 Config 문서를 혼용하지 않음

## 표시 규칙

| 정의 | 화면 |
| --- | --- |
| `key` | 저장·연결용 고유 키 · 자동 번역하지 않음 |
| `label`, `description` | 표시 이름·설명 · 사용자 문구 보존 |
| `unit` | 입력칸 옆 단위 · 자동 단위 변환 없음 |
| `number`, `integer` | 숫자·정수 입력 |
| `string` | 문자 입력 |
| `boolean` | 사용 여부 선택 |
| `object`, `fields` | 중첩된 항목 묶음 |
| `array`, `items` | 행 목록 · `+`로 선언된 구조의 빈 행 추가 |
| `widget: "vector3"` | 길이 3인 숫자 배열을 XYZ 입력으로 표시 |
| `enum` | 단일 선택 |
| `item_enum` | 복수 선택 |
| `minimum`, `maximum`, `step` | 숫자 입력 범위·간격 |
| `required` | 필수 표시 · 최종 실행 요건은 해당 실행기에서 확인 |
| `nullable` | 초안의 미입력 `null` 허용 |
| `readonly` | 입력 잠금 |
| `user_defined` | 사용자 추가 항목 · 표시 이름 더블클릭으로 변경 |

- 순서: Template의 `fields` 순서 → 추가된 Config 키 순서
- 새 키는 보존하고 자료형에 맞는 입력으로 표시 · 프로젝트 이름으로 양식을 고르지 않음
- 스키마 없는 빈 배열은 행 구조를 추정할 수 없음 · `items`로 자료형과 하위 항목 선언 권장
- 기존 좌표·온도별 물성 표·형상 형식은 호환 규칙으로 표시
- 실행 기록은 읽기 전용 · 기본 항목의 이름·형식은 UI에서 변경하지 않음
- 요소의 추가 속성 레코드는 `name`·`type`·`unit`·`value` 사용 · 벡터·목록·범위 정의는 `input`에 보존
- 표시 정의는 저장 Config의 `_studio.field_metadata`에도 보존 · 계산 물성값으로 사용하지 않음
- 예약 키·잘못된 자료형·중복 필드·지원하지 않는 표시 방식은 [오류 코드](ERROR-CODES.md)로 안내
- 원본 JSON 객체의 같은 키를 여러 번 쓰지 않음 · 중복 키는 JSON 파서에서 마지막 값으로 처리될 수 있음
- 제한: 가져오기 1 MB · 중첩 16단계 · 필드 512개 · 배열 10000개

## 확장 예시

- 내보낸 스키마의 필요한 그룹에 추가할 필드 예시 · 다른 필드는 그대로 유지
- `items`의 빈 값은 새 행의 양식 · 물리 기본값을 가정하지 않음

```json
{
  "key": "custom_sensors",
  "label": "관측점",
  "type": "array",
  "user_defined": true,
  "value": [],
  "items": {
    "type": "object",
    "fields": [
      {"key": "name", "label": "이름", "type": "string", "value": ""},
      {
        "key": "location",
        "label": "위치",
        "type": "array",
        "widget": "vector3",
        "unit": "m",
        "value": [null, null, null]
      }
    ]
  }
}
```

- `config`의 대응 위치에 `"custom_sensors": []` 추가
- **JSON 저장** 후 `+` 선택 → 이름·X·Y·Z 입력칸 생성
- 자료형을 바꾸려면 `config_schema`와 `config`를 함께 변경 · 값만 바꾸는 JSON에서는 기존 자료형 유지

## 추가 속성

- **물질 상태** 선택 → **물성 및 초기 조건 → + 속성 → 속성 종류**
- 분류: 공통 정보·재료 물성·초기 조건·열전달·다공성 및 표면·전기·상 경계 및 상변화·난류·물성 표
- 표시 후보는 물질 상태·솔버·유동 모델·상변화 사용 여부에 따라 필터링
- 상태 미지정: 공통 정보·밀도 후보 제공 · 상태를 선택하면 해당 후보 추가
- 스칼라 속성은 숫자 입력 · 초기 속도는 XYZ · 온도별 물성은 행 표 · 대류 열전달은 계수·기준 온도 묶음
- 후보에 없으면 **직접 정의** 또는 스키마 확장 · 실제 계산 반영은 실행 어댑터 확인 필요

## 에이전트 조회

- `CFDAgent.configRules()`: 지원 규칙 1회 조회
- `CFDAgent.configDocument()`: 열린 편집기의 내보내기 문서 · 필요한 시점에만 조회
- `CFDAgent.status()`: 화면·일시정지·오류만 간결하게 조회 · 전체 Config·로그·입력 목록 생략
- `CFDAgent.errorInfo(code)`: 오류 하나의 원인·해결 방법 조회
- JSON 전달·적용은 기존 `config.json.open`, `config.json.fill`, `config.json.apply` 사용
- 사용자 화면의 같은 초안에 반영 · 최종 저장과 계산 시작은 별도 단계
