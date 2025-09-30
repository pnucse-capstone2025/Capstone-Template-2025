## 1. 프로젝트 배경
### 1.1. 국내외 시장 현황 및 문제점
현대 자동차는 자율주행 및 커넥티드카 기술 발전으로 전자화 시대에 접어들었지만, 이로 인해 새로운 보안 위협에 노출되고 있습니다. 특히, 기존 차량 통신 프로토콜인 CAN(Controller Area Network)은 경량성과 실시간성을 위해 설계되어 데이터 위·변조 및 재전송 공격에 취약하다는 한계가 있습니다. 실제로 2015년 Jeep Cherokee 원격 해킹 사건은 이러한 취약점을 보여주며 자동차 보안의 시급성을 부각했습니다. 또한, 실제 차량 환경에서 보안 알고리즘을 테스트하는 것은 비용과 위험이 커서 체계적인 시뮬레이션 환경이 부족한 실정입니다.

### 1.2. 필요성과 기대효과
본 프로젝트는 Simulink를 활용해 가상의 자동차 통신 환경을 구축하고, 여기에 최적화된 보안 기술을 적용, 검증하는 프레임워크를 제공합니다. 이를 통해 실제 차량 실험의 비용과 위험을 줄이고, 자원 제약적인 ECU 환경에 적합한 보안 알고리즘의 성능을 평가할 수 있습니다. 궁극적으로 자동차 보안 기술의 신뢰성을 높여 자율주행차 및 커넥티드카의 안전한 상용화에 기여할 것으로 기대됩니다.

## 2. 개발 목표
### 2.1. 목표 및 세부 내용
본 프로젝트의 궁극적인 목표는 MATLAB/Simulink 환경에서 CAN-FD 기반 자동차 전장부품 데이터 전송 시스템을 설계하고, 여기에 보안 알고리즘(HMAC-SHA256, Freshness Counter)을 적용하여 실제 차량 내부 통신 환경에서 발생할 수 있는 위협을 모의 검증하는 것입니다. 이를 위해 송신 ECU에서 생성된 데이터(AppData, Freshness)가 수신 ECU에서 동일한 MAC 연산을 통해 검증되도록 하여, 데이터 위변조 및 재전송 공격을 차단하고, 정상적으로 인증된 데이터만이 제어 시스템에 입력되는 보안 게이트 구조를 구현합니다.

특히, 본 연구는 CAN-FD 통신의 특성과 제약을 고려하여 무결성 검증(HMAC-SHA256)과 신선도 검증(Freshness Counter)을 동시에 적용하는 메커니즘을 설계함으로써 기존 CAN 환경에서 부족했던 보안성을 강화합니다. 이 과정을 통해 공격 시나리오(위변조, 재전송, MAC 불일치)에 대한 ECU 동작을 실험적으로 검증하고, 보안 모듈의 민감성 및 동기화 필요성을 체계적으로 분석합니다.

또한, 기존의 단일 프로토콜 기반 보안 검증에서 나아가 본 프로젝트는 Ethernet 통신 경로를 병렬로 구현하여 CAN-FD와 함께 운용할 수 있는 시뮬레이션 환경을 마련합니다. Ethernet 기반 전송은 고속·대용량 데이터 처리에 강점을 가지는 반면, 외부 네트워크와의 연결로 보안 위협이 크다는 특성을 지닙니다. 따라서 본 연구에서는 CAN-FD와 Ethernet 경로를 동시에 모델링하고 동일한 보안 알고리즘을 병렬 적용하여, 차세대 차량 네트워크에서의 다중 프로토콜 환경 보안성 검증을 목표로 합니다.

결국 본 프로젝트는 Simulink 시뮬레이션 환경에서 CAN-FD와 Ethernet을 통합한 보안 프레임워크를 제시하고, 이를 통해 다양한 보안 알고리즘의 적용 가능성을 실험적으로 검토함으로써 향후 자율주행차 및 커넥티드카 환경에서 신뢰성 높은 ECU 보안 구조를 구현할 수 있는 기반을 마련하고자 합니다.

### 2.2. 기존 서비스 대비 차별성
기존의 단일 프로토콜 기반 연구와 달리, 이 프로젝트는 CAN-FD와 Ethernet 경로를 병렬로 구현하여 두 통신 환경을 동시에 시뮬레이션하고 검증할 수 있습니다. 또한, 단순한 시뮬레이션에 그치지 않고, MATLAB App Designer로 UI를 설계하여 보안 검증 결과를 직관적으로 시각화하고, 사용자가 직접 공격 시나리오를 제어할 수 있는 실험적 환경을 제공합니다.

### 2.3. 사회적 가치 도입 계획
이 프로젝트는 자동차 네트워크 보안의 취약점을 해결함으로써 운전자와 승객의 안전을 보장하는 데 기여합니다. 또한, 자율주행 및 커넥티드카 기술의 신뢰성을 높여 관련 산업의 지속 가능한 성장을 위한 기반을 마련합니다.

## 3. 시스템 설계
### 3.1. 시스템 구성도
이 시스템은 크게 송신부(TX)와 수신부(RX)로 구성되어 있습니다.

- 송신부 (TX): BrakeSensorECU 역할을 모사하며, 센서 데이터를 생성하고, HMAC-SHA256 기반 MAC과 Freshness Counter를 추가하여 CAN-FD 및 Ethernet(UDP) 프레임으로 구성해 전송합니다.

- 수신부 (RX): ABSECU 역할을 수행하며, 수신된 프레임에서 데이터를 분리한 후 MAC과 Freshness를 검증합니다. 검증에 성공한 데이터만 ECU 로직으로 전달하는 Fail-Safe 구조를 구현합니다.

### 3.2. 사용 기술
3.2.1 개발 환경

(1) MATLAB/Simulink

- 자동차 전장부품(Brake ECU, Dashboard ECU 등) 모델링

- CAN-FD 및 Ethernet 통신 시뮬레이션

- Vehicle Network Toolbox 활용: CAN-FD Pack/Unpack, UDP/TCP 전송 모델링

- 보안 알고리즘(HMAC-SHA256, Freshness Counter) 삽입 및 검증 환경 구축

(2) VS Code

- MATLAB 스크립트와 일부 보안 알고리즘 테스트 코드 관리

(3) MATLAB App Designer

- UI 설계(보안 알고리즘 선택, 시뮬레이션 결과 시각화)

3.2.2 사용 언어

- MATLAB: Simulink 모델링, CAN-FD/Ethernet 통신, 보안 알고리즘 구현 및 결과 분석

- Python 3.10: 보조적 알고리즘 검증, 데이터 분석, 시각화

3.2.3 사용 기술

(1) 통신 및 보안

- Vehicle Network Toolbox: CAN-FD 프레임 생성, ECU 간 통신 모델링

- Instrument Control Toolbox: UDP/TCP 블록 활용 → Ethernet 통신 경로 구현

- 보안 알고리즘: HMAC-SHA256 기반 무결성 검증, Freshness Counter 기반 리플레이 공격 방어

(2) UI 및 시각화

- MATLAB App Designer: 알고리즘 선택, 시뮬레이션 결과(무결성, Freshness, 지연) 시각화

- Scope/Display 블록: ECU 출력값과 보안 검증 결과 모니터링

(3) 배포 및 환경 관리

- Docker(선택적): MATLAB Runtime 기반 컨테이너 환경에서 Simulink 실행 가능성 검토

- GitHub: Simulink 모델 및 코드 관리, 버전 관리

## 4. 개발 결과
### 4.1 전체 시스템 흐름도

본 시스템은 차량 내 ECU 간의 보안 통신을 Simulink 환경에서 모델링하고, CAN-FD와 Ethernet 경로를 병렬로 구현하여 다양한 공격 시나리오에 대응할 수 있는 구조를 설계하였다. 전체적인 데이터 흐름과 처리 단계는 아래와 같다.

1. **센서 데이터 생성**  
   - 송신부(TX ECU)에서 브레이크 페달의 **원시 데이터(Raw)** 와 **눌림 여부(Pressed)** 신호를 생성한다.  
   - 이 데이터는 이후 보안 모듈 입력으로 전달된다.

2. **보안 데이터 생성**  
   - Raw 데이터와 Pressed 데이터에 **Freshness Counter** 값을 결합한다.  
   - 해당 값을 입력으로 하여 **HMAC-SHA256 기반 MAC(Message Authentication Code)** 을 생성한다.  
   - 이 과정을 통해 무결성과 신선도를 동시에 확보한다.

3. **데이터 전송**  
   - 생성된 데이터(AppData, Pressed, Freshness, MAC)를  
     - **CAN-FD 프레임(최대 64 Byte)**  
     - **Ethernet(UDP 기반 PDU)**  
     두 개의 경로에 병렬로 담아 전송한다.  
   - CAN-FD는 실시간성과 호환성을, Ethernet은 고속·대용량 전송을 담당한다.

4. **데이터 수신**  
   - 수신부(RX ECU)는 두 개의 경로(CAN-FD / UDP)를 통해 데이터를 수신한다.  
   - Vehicle Network Toolbox(CAN Unpack) 및 Instrument Control Toolbox(UDP Receive)를 통해 패킷을 해석한다.

5. **보안 검증**  
   - 수신 ECU는 동일한 **HMAC-SHA256 연산**을 수행하여 송신부에서 생성된 MAC과 비교한다.  
   - 동시에 Freshness Counter 값의 증가 여부를 확인하여 **리플레이 공격 여부**를 판단한다.

6. **Fail-Safe 처리**  
   - 검증에 **성공한 데이터만** ECU 로직으로 전달된다.  
   - 검증에 실패한 데이터(위·변조, 재전송 등)는 즉시 차단하여 시스템에 반영되지 않도록 한다.

7. **결과 시각화**  
   - **Lamp**: 데이터 검증 성공/실패를 색상으로 표시 (예: Green=정상, Red=실패).  
   - **Gauge**: Brake Force 값을 실시간으로 시각화하여 운전자의 제동 상태를 확인할 수 있다.  
   - **UI(App Designer 연동)**: 시뮬레이션 결과를 직관적으로 표시하고, 알고리즘별 성능 비교가 가능하다.

이와 같은 흐름도를 통해 CAN-FD와 Ethernet 병렬 경로 환경에서의 보안 통신을 실험적으로 검증하였으며, 리플레이 공격·위변조·DoS 공격 상황에 대한 ECU 반응을 시뮬레이션하였다.

### 4.2. 기능 설명 및 주요 기능 명세서
|기능|입력|출력|설명|
|-----|---|---|---|
|MAC 생성|appdata(3B), freshness(4B)|mac8(8B)|HMAC-SHA256을 계산하고 상위 8바이트를 추출해 MAC을 생성합니다.|
|Freshness 검증|currFV(현재 값), lastFV(이전 값)|ok(Boolean)|currFV가 lastFV보다 크고, 증가 폭이 허용 윈도우(W=1024) 내에 있는지 확인합니다.|
데이터 게이팅|valid(Boolean), data(Raw, Pressed)|data or default	|valid 값이 true일 때만 데이터를 통과시키고, false일 경우 기본값(0)을 출력합니다.|

### 4.3. 산업체 멘토링 의견 및 반영 사항

- 과제 목표 명확화: 피드백에 따라 연구 범위를 Simulink 기반 보안 통신 환경 구축, CAN/Ethernet 시뮬레이션, CAN 프로토콜 보안 강화의 3가지 핵심 목표로 재정립했습니다.

- 알고리즘 합리화: 국제 표준 문제로 채택이 어려운 SPECK 대신, 국내 개발 경량 블록암호인 CHAM 알고리즘을 향후 검토 대상으로 반영하여 실용성을 높였습니다.

- 역할 분담 구체화: 멘토링에서 긍정적으로 평가받은 역할 분담 체계를 유지하면서 **Ethernet 및 TLS 관련 보안 기능(홍재왕), CAN-FD 기반 통신 및 Freshness 검증(석재영), UI 개발 및 워크플로우 설계(레퐁푸)**로 세부 작업을 명확히 구분했습니다.

## 5. 설치 및 실행 방법
### 5.1. 설치절차 및 실행 방법
(1) 사전 준비

- MATLAB R2023b 이상, Simulink 설치 필요

- Vehicle Network Toolbox, Instrument Control Toolbox 설치 필요

- (선택) Docker Desktop 설치 후 MATLAB Runtime 환경 구성 가능

(2) 프로젝트 다운로드

git clone https://github.com/사용자이름/저장소이름.git
cd 저장소이름


(3) Simulink 모델 실행

- MATLAB 실행 → project.slx (예: CAN_FD_Security.slx) 열기

- 상단 툴바에서 Run 버튼 클릭

- App Designer UI(security_UI.mlapp) 실행 시 알고리즘 선택 및 결과 시각화 가능

(4) 포트 정보

- CAN-FD: Simulink 내부 가상 네트워크 환경 기반

- Ethernet(UDP): 기본 포트 5000 사용 (필요 시 UDP Send / UDP Receive 블록 속성에서 수정 가능)


### 5.2. 오류 발생 시 해결 방법

(1) Toolbox 누락 오류

- 오류 메시지에 Unrecognized block 발생 시 → Add-On Explorer에서 해당 Toolbox 설치

- 예: Vehicle Network Toolbox, Instrument Control Toolbox

(2) 포트 충돌 오류 (UDP)

- Port already in use 오류 발생 시 → 다른 포트(예: 6000)로 변경 후 재실행

(3) 보안 알고리즘 오류

- HMAC-SHA256 연산 불일치 발생 시 → 송신부/수신부의 Key 및 Freshness Counter 초기값이 동일한지 확인

(4) Docker 실행 오류 (선택적 환경)

- MATLAB Runtime 이미지 버전 불일치 시 → docker pull mathworks/matlab-runtime:r2023b 명령어로 최신 이미지 다운로드


## 6. 소개 자료 및 시연 영상
### 6.1. 프로젝트 소개 자료
https://github.com/pnucse-capstone2025/Capstone-2025-team-39/blob/main/docs/03.%EB%B0%9C%ED%91%9C%EC%9E%90%EB%A3%8C/autoshield_presentation.pdf
### 6.2. 시연 영상
https://youtu.be/P9r13Io3QSs?si=FCTwgvSGJHzuFtQ8

## 7. 팀 구성
### 7.1. 팀원별 소개 및 역할 분담

(1) 홍재왕 (CAN 프로토콜 담당)

- CAN 프로토콜 메시지 구조와 취약점(스푸핑, 리플레이) 분석

- Simulink 기반 CAN 통신 시뮬레이션 구현

- MAC, XOR, SHA-256 적용을 통한 유효 메시지 전송 보장 및 초기 구현 완료

- 보안 알고리즘 성능 비교(지연 시간, 메모리 사용) 참여

(2) 석재영 (TCP/IP, Ethernet 담당)

- Automotive Ethernet 및 TCP/IP 특성과 V2X 보안 요구사항 분석

- Simulink 기반 Ethernet 통신 시뮬레이션 구현

- TLS 간소화 버전 적용 테스트 및 데이터 흐름 분석

- 알고리즘 성능 비교 지원

(3) 레퐁푸 (Simulink/시각화 담당)

- Simulink 환경 구축 및 ECU, 센서, 계기판 메시지 흐름 모델링

- 보안 알고리즘 통합 워크플로우 설계

- MATLAB App Designer 기반 UI 개발(알고리즘 선택, 성능 시각화)

- 보고서 작성 및 문서화 주도

※ 기존 역할에서 SHA-256, Gauge/Slider를 활용한 통신 흐름, 초기 CAN 보안 구현을 반영하였으며, 국가보안기술연구소 피드백에 따라 LLM 적용은 제외하였습니다. 역할은 프로젝트 일정에 따라 유연하게 조정하였습니다.

### 7.2. 팀원 별 참여 후기

- 홍재왕:
CAN 프로토콜의 취약점을 직접 구현·검증하며, 단순한 이론 검토가 아니라 실제 보안 메커니즘이 어떻게 적용되는지 체감할 수 있었습니다. 특히 HMAC-SHA256과 Freshness Counter의 성능 차이를 비교하면서, 차량 통신 보안에서 “성능과 안전성 간의 균형”이 핵심임을 배웠습니다.

- 석재영:
Ethernet 경로와 TLS 적용 가능성을 실험하며, 차량 네트워크가 단일 프로토콜을 넘어 다중 프로토콜 환경으로 확장된다는 점을 확인할 수 있었습니다. TCP/IP 기반 시뮬레이션에서 발생한 지연 문제를 최적화하는 과정은 어려웠지만, 협업을 통해 해결하며 실무적인 통찰을 얻을 수 있었습니다.

- 레퐁푸:
Simulink와 App Designer를 활용하여 UI 및 시각화를 구현하면서, 보안 검증 결과를 직관적으로 표현하는 것이 얼마나 중요한지 알게 되었습니다. Lamp, Indicator, Gauge를 통해 Fail-Safe 동작을 확인했을 때 보람을 크게 느꼈습니다. 또한 문서화를 주도하며 팀의 결과물을 체계적으로 정리하는 경험을 쌓았습니다.

## 8. 참고 문헌 및 출처
[1] R. Bosch GmbH, CAN Specification Version 2.0, Stuttgart, Germany, 1991.
[2] ISO 11898-1, Road vehicles — Controller area network (CAN) — Part 1: Data link layer and physical signalling, International Organization for Standardization, Geneva, Switzerland, 2015.
[3] ISO 11898-7, Road vehicles — Controller area network (CAN) — Part 7: CAN FD data link layer specification, International Organization for Standardization, Geneva, Switzerland, 2015.
[4] MathWorks, Vehicle Network Toolbox Documentation: Simulink Support for CAN FD and Ethernet, MathWorks Inc., Natick, MA, USA, 2023. [Online]. Available: https://www.mathworks.com/help/vnt/
[5] M. Wolf, A. Weimerskirch, and C. Paar, "Security in Automotive Bus Systems," Proceedings of the Workshop on Embedded Security in Cars (ESCAR), pp. 1-12, 2004.
[6] C. Miller and C. Valasek, "Remote Exploitation of an Unaltered Passenger Vehicle," Black Hat USA, pp. 1-91, Aug. 2015.
[7] FIPS PUB 180-4, Secure Hash Standard (SHS), Federal Information Processing Standards Publication, National Institute of Standards and Technology (NIST), Gaithersburg, MD, 2015.
[8] H. Krawczyk, M. Bellare, and R. Canetti, "HMAC: Keyed-Hashing for Message Authentication," RFC 2104, Internet Engineering Task Force (IETF), Feb. 1997.
[9] H. Kopetz, Real-Time Systems: Design Principles for Distributed Embedded Applications, Springer, 2011.
[10] MathWorks, MATLAB Function Blocks and Code Generation for Embedded Systems, MathWorks Inc., Natick, MA, USA, 2023. [Online]. Available: https://www.mathworks.com/help/simulink/ug/matlab-function-block.html



