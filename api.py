from fastapi import FastAPI, HTTPException
from kubernetes import client, config # type: ignore
from kubernetes.client.exceptions import ApiException # type: ignore
import os, json, yaml
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional, List, Dict
import subprocess

app = FastAPI(title="Kubernetes Automation API", version="1.2")

# Kubernetes Connection
def connect_to_k8s_cluster(kubeconfig_path="~/.kube/config"):
    """
    Connect to the Kubernetes cluster using a kubeconfig file.

    Args:
        kubeconfig_path (str): Path to the kubeconfig file. Defaults to '~/.kube/config'.

    Returns:
        str: Success message if connection is established.

    Raises:
        HTTPException: If unable to connect to the Kubernetes cluster.
    """
    try:
        # Expand and validate kubeconfig path
        expanded_path = os.path.expanduser(kubeconfig_path)
        
        # Load Kubernetes config
        config.load_kube_config(config_file=expanded_path)
        
        # Check cluster access by fetching API server info
        version_api = client.VersionApi()
        server_version = version_api.get_code()
        
        print("✅ Connected to Kubernetes cluster.")
        return f"✅ Kubernetes cluster connection successful. Server version: {server_version.git_version}"
    except ApiException as e:
        print(f"❌ Kubernetes API error: {e}")
        raise HTTPException(status_code=500, detail=f"Kubernetes API error: {e}")
    except FileNotFoundError as e:
        print(f"❌ Kubeconfig file not found at path: {kubeconfig_path}")
        raise HTTPException(status_code=404, detail=f"Kubeconfig file not found at {kubeconfig_path}: {e}")
    except Exception as e:
        print(f"❌ Failed to connect to Kubernetes cluster: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Kubernetes cluster: {e}")

def install_helm_and_keda():
    """
    Installs Helm and KEDA in the Kubernetes cluster if not already installed.
    
    Raises:
        HTTPException: If any step of installation or verification fails.
    """
    try:
        # Install Helm
        print("🔄 Checking if Helm is installed...")
        helm_version = subprocess.run(["helm", "version", "--short"], capture_output=True, text=True)
        if helm_version.returncode != 0:
            raise HTTPException(status_code=500, detail="Helm is not installed or not accessible.")
        print(f"✅ Helm installed: {helm_version.stdout.strip()}")

        # Add KEDA Helm Repo
        print("🔄 Adding KEDA Helm repository...")
        subprocess.run(["helm", "repo", "add", "kedacore", "https://kedacore.github.io/charts"], check=True)
        subprocess.run(["helm", "repo", "update"], check=True)
        print("✅ KEDA Helm repository added and updated.")

        # Install KEDA
        print("🔄 Installing KEDA via Helm...")
        subprocess.run(
            ["helm", "install", "keda", "kedacore/keda", "--namespace", "keda", "--create-namespace"],
            check=True,
        )
        print("✅ KEDA installed successfully.")

        # Verify KEDA installation
        print("🔄 Verifying KEDA operator is running...")
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_namespaced_pod(namespace="keda", label_selector="app=keda-operator").items
        if not pods:
            raise HTTPException(status_code=500, detail="KEDA operator pod not found in 'keda' namespace.")
        for pod in pods:
            if pod.status.phase != "Running":
                raise HTTPException(
                    status_code=500, detail=f"KEDA operator pod '{pod.metadata.name}' is not running."
                )
        print("✅ KEDA operator is running.")

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Helm command failed: {e.stderr}")
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Kubernetes API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error installing Helm or KEDA: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the application lifecycle."""
    # Startup logic
    try:
        print("🔄 Connecting to Kubernetes cluster on startup...")
        connect_to_k8s_cluster(kubeconfig_path="~/.kube/config")
        print("✅ Connected to Kubernetes cluster.")
    except Exception as e:
        print(f"❌ Failed to connect to Kubernetes cluster during startup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"❌ Failed to connect to Kubernetes, Message: {str(e)}"
        )
    
    yield  # Run the application

    # Shutdown logic (if any)
    print("🛑 Application shutting down...")

app.lifespan = lifespan

@app.get("/check-cluster", status_code=200)
def check_cluster():
    """Endpoint to verify Kubernetes cluster connection."""
    try:
        message = connect_to_k8s_cluster(kubeconfig_path="~/.kube/config")
        return {"message": message}
    except HTTPException as e:
        return {"error": e.detail}

# Define Pydantic model for deployment request
class DeploymentRequest(BaseModel):
    image: str
    name: str
    namespace: str
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    cpu_request: Optional[str] = None
    memory_request: Optional[str] = None
    ports: List[int]  # Comma-separated list of ports
    environment_variables: Optional[Dict[str, str]] = None
    min_replicas: int
    max_replicas: int
    event_source_type: str
    event_source_metadata: str  # JSON-like string for metadata

def load_yaml_template(file_path: str, replacements: dict):
    """
    Load a YAML file and replace placeholders with actual values.

    Args:
        file_path (str): Path to the YAML file.
        replacements (dict): Dictionary of placeholders and their values.

    Returns:
        dict: YAML content with placeholders replaced.
    """
    with open(file_path, "r") as file:
        content = yaml.safe_load(file)

    # Replace placeholders
    content_str = json.dumps(content)
    for placeholder, value in replacements.items():
        content_str = content_str.replace(f"{{{placeholder}}}", str(value))
    return json.loads(content_str)

@app.post("/deploy", status_code=201)
def deploy_application(deployment_request: DeploymentRequest):
    """
    Create a Kubernetes Deployment, Service, and KEDA ScaledObject with autoscaling.

    Each input field is provided as a query parameter.
    """
    try:
        # Kubernetes API clients
        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()
        custom_objects_api = client.CustomObjectsApi()
        # Define file paths
        deployment_file = "templates/deployment.yml"
        service_file = "templates/service.yml"
        scaled_object_file = "templates/scaledobject.yml"
        # Prepare replacements
        replacements = {
            "name": deployment_request.name,
            "namespace": deployment_request.namespace,
            "image": deployment_request.image,
            "cpu_request": deployment_request.cpu_request,
            "memory_request": deployment_request.memory_request,
            "cpu_limit": deployment_request.cpu_limit,
            "memory_limit": deployment_request.memory_limit,
            "port": deployment_request.ports[0],  # Assuming single port for example
            "env_name": list(deployment_request.environment_variables.keys())[0] if deployment_request.environment_variables else "",
            "env_value": list(deployment_request.environment_variables.values())[0] if deployment_request.environment_variables else "",
            "min_replicas": deployment_request.min_replicas,
            "max_replicas": deployment_request.max_replicas,
            "event_source_type": deployment_request.event_source_type,
            "event_source_metadata": json.dumps(deployment_request.event_source_metadata),
        }

        # Load and process YAML templates
        deployment = load_yaml_template(deployment_file, replacements)
        service = load_yaml_template(service_file, replacements)
        scaled_object = load_yaml_template(scaled_object_file, replacements)

        # Apply resources
        apps_v1.create_namespaced_deployment(namespace=deployment_request.namespace, body=deployment)
        core_v1.create_namespaced_service(namespace=deployment_request.namespace, body=service)
        custom_objects_api.create_namespaced_custom_object(
            group="keda.sh",
            version="v1alpha1",
            namespace=deployment_request.namespace,
            plural="scaledobjects",
            body=scaled_object,
        )

        return {"message": f"Deployment {deployment_request.name} created successfully."}
        # # Parse ports
        # ports_list = [int(port.strip()) for port in ports.split(",")]

        # # Deployment
        # deployment = {
        #     "apiVersion": "apps/v1",
        #     "kind": "Deployment",
        #     "metadata": {"name": name, "namespace": namespace},
        #     "spec": {
        #         "replicas": 1,
        #         "selector": {"matchLabels": {"app": name}},
        #         "template": {
        #             "metadata": {"labels": {"app": name}},
        #             "spec": {
        #                 "containers": [
        #                     {
        #                         "name": name,
        #                         "image": image,
        #                         "resources": {
        #                             "requests": {"cpu": cpu_request, "memory": memory_request},
        #                             "limits": {"cpu": cpu_limit, "memory": memory_limit},
        #                         },
        #                         "ports": [{"containerPort": port} for port in ports_list],
        #                     }
        #                 ]
        #             },
        #         },
        #     },
        # }
        # apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)

        # # Service
        # service = {
        #     "apiVersion": "v1",
        #     "kind": "Service",
        #     "metadata": {"name": name, "namespace": namespace},
        #     "spec": {
        #         "selector": {"app": name},
        #         "ports": [{"protocol": "TCP", "port": port, "targetPort": port} for port in ports_list],
        #         "type": "LoadBalancer",
        #     },
        # }
        # core_v1.create_namespaced_service(namespace=namespace, body=service)

        # # KEDA ScaledObject
        # scaled_object = {
        #     "apiVersion": "keda.sh/v1alpha1",
        #     "kind": "ScaledObject",
        #     "metadata": {"name": f"{name}-scaledobject", "namespace": namespace},
        #     "spec": {
        #         "scaleTargetRef": {"name": name},
        #         "minReplicaCount": min_replicas,
        #         "maxReplicaCount": max_replicas,
        #         "triggers": [{"type": event_source_type, "metadata": eval(event_source_metadata)}],
        #     },
        # }
        # custom_objects_api.create_namespaced_custom_object(
        #     group="keda.sh",
        #     version="v1alpha1",
        #     namespace=namespace,
        #     plural="scaledobjects",
        #     body=scaled_object,
        # )

        # return {
        #     "message": f"Deployment {name} created successfully.",
        #     "details": {
        #         "namespace": namespace,
        #         "image": image,
        #         "ports": ports_list,
        #         "autoscaling": {"min_replicas": min_replicas, "max_replicas": max_replicas},
        #         "event_source": {"type": event_source_type, "metadata": eval(event_source_metadata)},
        #     },
        # }
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Kubernetes API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during deployment creation: {e}")

@app.get("/health/{namespace}/{deployment_name}")
def get_health_status(namespace: str, deployment_name: str):
    """Retrieve the health status of a Kubernetes deployment."""
    try:
        apps_v1 = client.AppsV1Api()
        deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        available_replicas = deployment.status.available_replicas or 0
        desired_replicas = deployment.spec.replicas

        return {
            "deployment_name": deployment_name,
            "namespace": namespace,
            "available_replicas": available_replicas,
            "desired_replicas": desired_replicas,
        }
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving deployment health status: {e}")
#Get all the namespaces
@app.get("/namespaces", status_code=200)
def get_namespaces():
    """Fetch all namespaces in the Kubernetes cluster."""
    try:
        core_v1 = client.CoreV1Api()
        namespaces = core_v1.list_namespace()
        return {"namespaces": [ns.metadata.name for ns in namespaces.items]}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching namespaces: {e}")
# to get all the deployments in the namespace
@app.get("/deployments/{namespace}", status_code=200)
def get_deployments(namespace: str):
    """Fetch all deployments in a specific namespace."""
    try:
        apps_v1 = client.AppsV1Api()
        deployments = apps_v1.list_namespaced_deployment(namespace)
        return {"deployments": [deploy.metadata.name for deploy in deployments.items]}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching deployments: {e}")

#to get all the services in the namespace
@app.get("/services/{namespace}", status_code=200)
def get_services(namespace: str):
    """Fetch all services in a specific namespace."""
    try:
        core_v1 = client.CoreV1Api()
        services = core_v1.list_namespaced_service(namespace)
        return {"services": [svc.metadata.name for svc in services.items]}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching services: {e}")

#To get all the pods in the namespace
@app.get("/pods/{namespace}", status_code=200)
def get_pods(namespace: str):
    """Fetch all pods in a specific namespace."""
    try:
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_namespaced_pod(namespace)
        return {"pods": [pod.metadata.name for pod in pods.items]}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pods: {e}")

@app.put("/update-keda/{namespace}/{scaled_object_name}", status_code=200)
def update_keda_scaled_object(
    namespace: str,
    scaled_object_name: str,
    min_replicas: int,
    max_replicas: int,
    event_source_type: str,
    event_source_metadata: str  # JSON-like string for metadata
):
    """
    Update an existing KEDA ScaledObject configuration.
    """
    try:
        custom_objects_api = client.CustomObjectsApi()

        # Get the existing ScaledObject
        scaled_object = custom_objects_api.get_namespaced_custom_object(
            group="keda.sh",
            version="v1alpha1",
            namespace=namespace,
            plural="scaledobjects",
            name=scaled_object_name,
        )

        # Update the ScaledObject configuration
        scaled_object["spec"]["minReplicaCount"] = min_replicas
        scaled_object["spec"]["maxReplicaCount"] = max_replicas
        scaled_object["spec"]["triggers"] = [{"type": event_source_type, "metadata": eval(event_source_metadata)}]

        # Apply the updated ScaledObject
        custom_objects_api.replace_namespaced_custom_object(
            group="keda.sh",
            version="v1alpha1",
            namespace=namespace,
            plural="scaledobjects",
            name=scaled_object_name,
            body=scaled_object,
        )

        return {
            "message": f"ScaledObject '{scaled_object_name}' in namespace '{namespace}' updated successfully.",
            "details": {
                "min_replicas": min_replicas,
                "max_replicas": max_replicas,
                "event_source": {"type": event_source_type, "metadata": eval(event_source_metadata)},
            },
        }
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Error updating ScaledObject: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")