# ScreenGolfUsageSystem 배포 정보 (PythonAnywhere)

이 파일은 이후의 작업자(AI 포함)가 배포 환경을 쉽게 파악할 수 있도록 저장된 프로젝트 정보입니다.

## 📌 서버 정보
*   **호스팅**: PythonAnywhere
*   **사용자 계정 (Username)**: `WellnessCenter`
*   **프로젝트(Git) 경로**: `/home/WellnessCenter/screengolf-usage`

## 🚀 수동 배포 (업데이트) 가이드
소스 코드가 변경되어 GitHub 원격 저장소에 Push된 후, PythonAnywhere 서버에 최신 코드를 반영하려면 다음 절차를 따릅니다.

1. PythonAnywhere의 **Consoles** 탭에서 **Bash 콘솔**을 열거나 열려 있는 콘솔을 확인합니다.
2. 아래 명령어를 차례대로 입력 및 실행합니다.
```bash
cd /home/WellnessCenter/screengolf-usage
git pull origin main
```
3. 성공적으로 최신 코드를 당겨왔다면(Pull), 상단의 **Web** 탭으로 이동합니다.
4. 초록색 **[Reload]** 버튼(`Reload WellnessCenter.pythonanywhere.com`)을 클릭하여 서버를 재시작합니다.
5. 운영 중인 사이트에 접속하여 변경 사항이 정상적으로 반영되었는지 확인합니다.
