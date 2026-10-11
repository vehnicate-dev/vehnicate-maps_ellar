plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val h3Version = "4.5.0"
val h3AndroidNativeArtifacts by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
    isTransitive = false
}
val generatedH3JniLibs = layout.buildDirectory.dir("generated/h3-jni-libs")
val h3AndroidJar = h3AndroidNativeArtifacts.elements.map { it.single().asFile }
val extractH3AndroidNatives = tasks.register<Copy>("extractH3AndroidNatives") {
    from(h3AndroidJar.map { zipTree(it) }) {
        include("android-arm64/libh3-java.so")
        eachFile { path = "arm64-v8a/$name" }
    }
    from(h3AndroidJar.map { zipTree(it) }) {
        include("android-arm/libh3-java.so")
        eachFile { path = "armeabi-v7a/$name" }
    }
    into(generatedH3JniLibs)
}

android {
    namespace = "com.vehnicate.roadauditor"
    compileSdk = 36

    sourceSets.getByName("main").jniLibs.srcDir(generatedH3JniLibs)

    defaultConfig {
        applicationId = "com.vehnicate.roadauditor"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        val supabaseUrl = providers.gradleProperty("SUPABASE_URL")
            .orElse("https://mmjusghgeedycrrfdejg.supabase.co")
            .get()
        val supabaseKey = providers.gradleProperty("SUPABASE_PUBLISHABLE_KEY")
            .orElse("sb_publishable_unNgZxi4yyID9qAAy3d2dg_dGJLpv3N")
            .get()
        buildConfigField("String", "SUPABASE_URL", "\"$supabaseUrl\"")
        buildConfigField("String", "SUPABASE_PUBLISHABLE_KEY", "\"$supabaseKey\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

tasks.named("preBuild").configure {
    dependsOn(extractH3AndroidNatives)
}

dependencies {
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("com.google.android.gms:play-services-location:21.3.0")
    implementation("com.uber:h3:$h3Version")
    add(h3AndroidNativeArtifacts.name, "com.uber:h3:$h3Version")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
}
