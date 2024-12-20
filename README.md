# **Kubernetes Automation API**

This project provides a FastAPI-based RESTful API to automate Kubernetes operations, including deployments, services, and autoscaling using KEDA. The code is modular, with YAML templates for Kubernetes resource definitions.

## **Table of Contents**

- #### Features
- #### Prerequisites
- #### Installation
- #### Endpoints
- #### Usage
- #### YAML Templates
- #### Project Structure
- #### Error Handling

## **Features**

### 1. Dynamic Kubernetes Deployment:

- Create Kubernetes resources such as Deployments, Services, and ScaledObjects using FastAPI.
- Supports resource limits, requests, and environment variables.

### 2. Cluster Interaction:

- Verify cluster connection.
- Fetch namespaces, deployments, services, and pods.

### 3. KEDA Autoscaling:

- Integrates with KEDA to manage ScaledObjects dynamically.

### 4. Modular YAML Templates:

- Resource definitions are stored as YAML templates for better maintainability.

## **Prerequisites**

### 1. Kubernetes Cluster:

- Ensure you have access to a Kubernetes cluster.

### 2. Tools:

- kubectl and helm should be installed on your machine.

### 3. Python:

- Python 3.8 or above.

### 4. Dependencies:

- FastAPI
- Kubernetes Python Client
- PyYAML
- Pydantic

## **Installation**

### 1. Clone the repository:

```
git clone https://github.com/your-repo/kubernetes-automation-api.git
cd kubernetes-automation-api
```

### 2. Install Python dependencies:

```
pip install -r requirements.txt
```

### 3.Install KEDA in the cluster:

```helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 4. Verify KEDA installation:

```
kubectl get pods -n keda
```

## **Endpoints**

### 1. /check-cluster

**Method:** GET

**Description:** Verifies the connection to the Kubernetes cluster.

**Response:**

```
{
  "message": "✅ Kubernetes cluster connection successful. Server version: v1.22.2"
}
```

### 2. /namespaces

**Method:** GET

**Description:** Lists all namespaces in the cluster.

**Response:**

```
{
  "namespaces": ["default", "kube-system", "keda"]
}
```

### 3. /deployments/{namespace}

**Method:** GET

**Description:** Lists all deployments in the specified namespace.
**Path Parameter:**

- namespace: Namespace to list deployments from.

**Response:**

```
{
  "deployments": ["app-deployment", "another-deployment"]
}
```

### 4. /services/{namespace}

**Method:** GET

**Description:** Lists all services in the specified namespace.

**Response:**

```
{
  "services": ["app-service", "another-service"]
}
```

### 5. /pods/{namespace}

**Method:** GET

**Description:** Lists all pods in the specified namespace.

**Response:**

```
{
  "pods": ["app-pod-1", "app-pod-2"]
}
```

### 6. /deploy

**Method:** POST

**Description:** Creates a Kubernetes deployment, service, and ScaledObject using user-defined parameters.

**Request Body:**

```
{
  "name": "my-app",
  "namespace": "default",
  "image": "nginx:latest",
  "cpu_request": "200m",
  "memory_request": "256Mi",
  "cpu_limit": "500m",
  "memory_limit": "512Mi",
  "ports": [80],
  "min_replicas": 1,
  "max_replicas": 5,
  "event_source_type": "kafka",
  "event_source_metadata": "{\"topic\": \"my-topic\", \"bootstrapServers\": \"kafka:9092\"}"
}
```

### 7. /update-keda/{namespace}/{scaled_object_name}

**Method:** PUT

**Description:** Updates an existing ScaledObject configuration.

**Path Parameters:**

- namespace: Namespace of the ScaledObject.
- scaled_object_name: Name of the ScaledObject.

**Request Body:**

```
{
  "min_replicas": 2,
  "max_replicas": 10,
  "event_source_type": "nginx",
  "event_source_metadata": "{\"topic\": \"new-topic\", \"bootstrapServers\": \"nginx:80\"}"
}
```

## **Usage**

1. Start the FastAPI server:

```
python -m uvicorn api:app --reload --port 8000 --server 0.0.0.0
```

2. Access the API docs at: http://127.0.0.1:8000/docs

## **YAML Templates**

The following YAML templates are used for creating Kubernetes resources:

### **Deployment**

File: templates/deployment.yml

### **Service**

File: templates/service.yml

### **ScaledObject**

File: templates/scaledobject.yml

Refer to the code section for details.

## **Project Structure**

```
k8s-automation-api/
├── api.py                 # Main application logic
├── requirements.txt        # Python dependencies
├── templates/              # YAML templates for Kubernetes resources
│   ├── deployment.yml
│   ├── service.yml
│   ├── scaledobject.yml
├── README.md               # Documentation
```

## **Error Handling**

**1. Cluster Connection:**

- Returns error codes 500 or 404 if the cluster connection fails.

**2. Resource Creation:**

- Returns detailed error messages for any failed Kubernetes API operations.

**3. Validation:**

Uses Pydantic models to validate API inputs.

## **Images**

After Running the Fast Api check the below Images how to test or create the deployments.

**1.** the home page of the FastApi

![Screenshot](images/image1.png)

**2.**/deploy url is to deploy the deployment,
already the path of the k8s templates defined in the code. the input is should be the json format.

![Screenshot](images/image2.png)

**3**/update-keta url is to update the existing the keda 

![Screenshot](images/image3.png)

# Thank You!
