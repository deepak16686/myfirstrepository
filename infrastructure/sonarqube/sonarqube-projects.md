# SonarQube Projects - Legacy Modernization Platform

**SonarQube URL:** `${SONARQUBE_URL}` (default http://localhost:9002)
**Username:** `${SONARQUBE_USERNAME}`  (default `admin`)
**Password:** `${SONARQUBE_PASSWORD}`  ← set in `.env` / Vault, never commit real value

> All per-project tokens below have been redacted. Real tokens live in Vault at
> `secret/devops/sonarqube/<project-key>` (or CI/CD masked variable
> `SONAR_TOKEN_<PROJECT_KEY_UPPERSNAKE>`). See
> `devops-tools-backend/docs/SECRET_ROTATION.md` for rotation procedure.

---

## Project Details

### Legacy-Banking-Core
- **Project Key:** `legacy-banking-core`
- **Description:** Legacy mainframe banking system
- **Token:** `${SONAR_TOKEN_LEGACY_BANKING_CORE}`  *(stored at `vault:secret/devops/sonarqube/legacy-banking-core#token`)*
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-banking-core`

### Legacy-Insurance-Policy
- **Project Key:** `legacy-insurance-policy`
- **Description:** Old insurance policy management
- **Token:** `${SONAR_TOKEN_LEGACY_INSURANCE_POLICY}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-insurance-policy`

### Legacy-Retail-POS
- **Project Key:** `legacy-retail-pos`
- **Description:** Point of sale system from 2005
- **Token:** `${SONAR_TOKEN_LEGACY_RETAIL_POS}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-retail-pos`

### Legacy-Healthcare-Records
- **Project Key:** `legacy-healthcare-records`
- **Description:** Patient records system
- **Token:** `${SONAR_TOKEN_LEGACY_HEALTHCARE_RECORDS}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-healthcare-records`

### Legacy-CRM-System
- **Project Key:** `legacy-crm-system`
- **Description:** Customer relationship management
- **Token:** `${SONAR_TOKEN_LEGACY_CRM_SYSTEM}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-crm-system`

### Legacy-ERP-Finance
- **Project Key:** `legacy-erp-finance`
- **Description:** Financial ERP modules
- **Token:** `${SONAR_TOKEN_LEGACY_ERP_FINANCE}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-erp-finance`

### Legacy-Inventory-Manager
- **Project Key:** `legacy-inventory-manager`
- **Description:** Warehouse inventory system
- **Token:** `${SONAR_TOKEN_LEGACY_INVENTORY_MANAGER}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-inventory-manager`

### Legacy-HR-Payroll
- **Project Key:** `legacy-hr-payroll`
- **Description:** Payroll processing system
- **Token:** `${SONAR_TOKEN_LEGACY_HR_PAYROLL}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-hr-payroll`

### Legacy-Telecom-Billing
- **Project Key:** `legacy-telecom-billing`
- **Description:** Telecom billing platform
- **Token:** `${SONAR_TOKEN_LEGACY_TELECOM_BILLING}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-telecom-billing`

### Legacy-Logistics-Tracker
- **Project Key:** `legacy-logistics-tracker`
- **Description:** Shipment tracking system
- **Token:** `${SONAR_TOKEN_LEGACY_LOGISTICS_TRACKER}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-logistics-tracker`

### Legacy-Hotel-Booking
- **Project Key:** `legacy-hotel-booking`
- **Description:** Hotel reservation system
- **Token:** `${SONAR_TOKEN_LEGACY_HOTEL_BOOKING}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-hotel-booking`

### Legacy-Flight-Reservation
- **Project Key:** `legacy-flight-reservation`
- **Description:** Airline booking platform
- **Token:** `${SONAR_TOKEN_LEGACY_FLIGHT_RESERVATION}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-flight-reservation`

### Legacy-Supply-Chain
- **Project Key:** `legacy-supply-chain`
- **Description:** Supply chain management
- **Token:** `${SONAR_TOKEN_LEGACY_SUPPLY_CHAIN}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-supply-chain`

### Legacy-Manufacturing-MES
- **Project Key:** `legacy-manufacturing-mes`
- **Description:** Manufacturing execution system
- **Token:** `${SONAR_TOKEN_LEGACY_MANUFACTURING_MES}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-manufacturing-mes`

### Legacy-Asset-Management
- **Project Key:** `legacy-asset-management`
- **Description:** Asset tracking system
- **Token:** `${SONAR_TOKEN_LEGACY_ASSET_MANAGEMENT}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-asset-management`

### Legacy-Document-Archive
- **Project Key:** `legacy-document-archive`
- **Description:** Document management system
- **Token:** `${SONAR_TOKEN_LEGACY_DOCUMENT_ARCHIVE}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-document-archive`

### Legacy-Email-Gateway
- **Project Key:** `legacy-email-gateway`
- **Description:** Email processing gateway
- **Token:** `${SONAR_TOKEN_LEGACY_EMAIL_GATEWAY}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-email-gateway`

### Legacy-Reporting-Engine
- **Project Key:** `legacy-reporting-engine`
- **Description:** Business intelligence reports
- **Token:** `${SONAR_TOKEN_LEGACY_REPORTING_ENGINE}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-reporting-engine`

### Legacy-Authentication-Service
- **Project Key:** `legacy-authentication-service`
- **Description:** User authentication system
- **Token:** `${SONAR_TOKEN_LEGACY_AUTHENTICATION_SERVICE}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-authentication-service`

### Legacy-Data-Warehouse
- **Project Key:** `legacy-data-warehouse`
- **Description:** Data warehouse ETL system
- **Token:** `${SONAR_TOKEN_LEGACY_DATA_WAREHOUSE}`
- **Dashboard:** `${SONARQUBE_URL}/dashboard?id=legacy-data-warehouse`

---

## Quick Access Commands
```bash
# Analyze with SonarScanner CLI — token sourced from env, never from this file
export SONAR_TOKEN="$(vault kv get -field=token secret/devops/sonarqube/<project-key>)"
sonar-scanner \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.sources=. \
  -Dsonar.host.url="${SONARQUBE_URL}" \
  -Dsonar.token="${SONAR_TOKEN}"

# Analyze with Maven
mvn sonar:sonar \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.host.url="${SONARQUBE_URL}" \
  -Dsonar.token="${SONAR_TOKEN}"
```

---
**Generated:** 2026-01-17 22:10:02 — *redacted on 2026-04-19 per secret-hygiene pass.*
