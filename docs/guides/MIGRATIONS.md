# 데이터베이스 마이그레이션

[문서 통합 목차](../README.md) · [개발·운영 가이드](README.md) · [설치·배포](SETUP.md)

실행할 Alembic 설정과 revision 파일은 저장소 루트의 [migrations](../../migrations/)에 유지합니다. 아래 명령은 저장소 루트에서 실행합니다.

운영 데이터베이스의 schema 변경은 Alembic revision으로 관리합니다. 최초 revision
`20260827_0001`은 데이터 소스·워크플로·챗봇·BI·벤치마크의 schema를 구성하며,
기존 사용자 데이터를 삭제하거나 이름을 바꾸지 않습니다. 후속 변경은 새 revision으로
추가하고, 이미 적용한 revision은 수정하지 않습니다.

```bash
# 저장소에 정의된 최신 revision 확인
uv run alembic heads

# 대상 DB 설정을 확인한 뒤 API·워커 배포 전에 적용
uv run alembic upgrade head
```

애플리케이션의 bootstrap schema 구성은 개발·테스트 초기화와 schema 차이 검증을
보조합니다. 운영 배포에서는 API·워커 실행 전에 migration을 적용하며, 런타임 초기화로
revision 적용을 대신하지 않습니다. 테스트에는 운영 DB가 아닌 별도 테스트 DB를 사용합니다.

현재 revision과 테이블 수는 [구현 기준선](../CURRENT_IMPLEMENTATION_BASELINE.md),
도메인별 소유권과 테이블 계약은
[`BP-503`](../blueprints/05_interface_blueprints/BP-503_database_erd_and_ddl.md)에서 확인합니다.
