# SonarQube Projects - Legacy Modernization Platform

**SonarQube URL:** http://localhost:9002
**Username:** admin
**Password:** ${SONARQUBE_ADMIN_PASSWORD}

---

## Project Details

### Legacy-Banking-Core
- **Project Key:** `legacy-banking-core`
- **Description:** Legacy mainframe banking system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-banking-core

### Legacy-Insurance-Policy
- **Project Key:** `legacy-insurance-policy`
- **Description:** Old insurance policy management
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-insurance-policy

### Legacy-Retail-POS
- **Project Key:** `legacy-retail-pos`
- **Description:** Point of sale system from 2005
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-retail-pos

### Legacy-Healthcare-Records
- **Project Key:** `legacy-healthcare-records`
- **Description:** Patient records system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-healthcare-records

### Legacy-CRM-System
- **Project Key:** `legacy-crm-system`
- **Description:** Customer relationship management
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-crm-system

### Legacy-ERP-Finance
- **Project Key:** `legacy-erp-finance`
- **Description:** Financial ERP modules
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-erp-finance

### Legacy-Inventory-Manager
- **Project Key:** `legacy-inventory-manager`
- **Description:** Warehouse inventory system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-inventory-manager

### Legacy-HR-Payroll
- **Project Key:** `legacy-hr-payroll`
- **Description:** Payroll processing system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-hr-payroll

### Legacy-Telecom-Billing
- **Project Key:** `legacy-telecom-billing`
- **Description:** Telecom billing platform
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-telecom-billing

### Legacy-Logistics-Tracker
- **Project Key:** `legacy-logistics-tracker`
- **Description:** Shipment tracking system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-logistics-tracker

### Legacy-Hotel-Booking
- **Project Key:** `legacy-hotel-booking`
- **Description:** Hotel reservation system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-hotel-booking

### Legacy-Flight-Reservation
- **Project Key:** `legacy-flight-reservation`
- **Description:** Airline booking platform
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-flight-reservation

### Legacy-Supply-Chain
- **Project Key:** `legacy-supply-chain`
- **Description:** Supply chain management
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-supply-chain

### Legacy-Manufacturing-MES
- **Project Key:** `legacy-manufacturing-mes`
- **Description:** Manufacturing execution system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-manufacturing-mes

### Legacy-Asset-Management
- **Project Key:** `legacy-asset-management`
- **Description:** Asset tracking system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-asset-management

### Legacy-Document-Archive
- **Project Key:** `legacy-document-archive`
- **Description:** Document management system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-document-archive

### Legacy-Email-Gateway
- **Project Key:** `legacy-email-gateway`
- **Description:** Email processing gateway
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-email-gateway

### Legacy-Reporting-Engine
- **Project Key:** `legacy-reporting-engine`
- **Description:** Business intelligence reports
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-reporting-engine

### Legacy-Authentication-Service
- **Project Key:** `legacy-authentication-service`
- **Description:** User authentication system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-authentication-service

### Legacy-Data-Warehouse
- **Project Key:** `legacy-data-warehouse`
- **Description:** Data warehouse ETL system
- **Token:** `${SONARQUBE_TOKEN}`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-data-warehouse

---

## Quick Access Commands
```powershell
# Analyze a project with Maven
mvn sonar:sonar \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.host.url=http://localhost:9002 \
  -Dsonar.login=<token>

# Analyze with SonarScanner CLI
sonar-scanner \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.sources=. \
  -Dsonar.host.url=http://localhost:9002 \
  -Dsonar.login=<token>
```

---
**Generated:** 2026-01-17 22:10:02
